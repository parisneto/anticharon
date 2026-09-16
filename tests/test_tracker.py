"""Tests for anticharon.tracker: the cache-aware, provider-routable pricing
engine (docs/plans/pricing-engine-v2/PLAN.md). All network calls are mocked --
`@pytest.mark.live` tests for the real API contracts live in
test_effective_pricing_backfill.py and test_policy_pricing.py.
"""

import json
from datetime import datetime, timezone

import pytest

from anticharon.tracker import run_tracker


def _write_shortlist(tmp_path, models):
    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({
        "shortlist": models,
        "weight_uncached_prompt": 0.232622,
        "weight_cached_prompt": 0.764478,
        "weight_completion": 0.0029,
    }), encoding="utf-8")
    return cfg_path


@pytest.fixture
def no_backfill(monkeypatch):
    """Backfill isn't the focus of these tests -- keep it a no-op (empty history)."""
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})


def test_run_tracker_skips_sentinel_priced_model(monkeypatch, tmp_path, no_backfill):
    """openrouter/auto-beta (a meta-router) lists pricing prompt/completion as "-1" --
    a real, live-verified case, not hypothetical. run_tracker must skip it rather
    than surface a negative $/1M as though it were the cheapest real price."""

    def fake_fetch_openrouter_models(timeout: float = 10.0):
        return {
            "openrouter/auto-beta": {
                "id": "openrouter/auto-beta",
                "canonical_slug": "openrouter/auto-beta",
                "pricing": {"prompt": "-1", "completion": "-1"},
            },
            "openai/gpt-5.6-luna": {
                "id": "openai/gpt-5.6-luna",
                "canonical_slug": "openai/gpt-5.6-luna-20260709",
                "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
            },
        }

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", fake_fetch_openrouter_models)
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])

    cfg_path = _write_shortlist(tmp_path, ["openrouter/auto-beta", "openai/gpt-5.6-luna"])
    result = run_tracker(dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True)

    model_ids = [p.model for p in result.prices_shortlist]
    assert "openrouter/auto-beta" not in model_ids
    assert "openai/gpt-5.6-luna" in model_ids
    assert all(p.price_1m >= 0 for p in result.prices_shortlist)


def test_run_tracker_effective_price_uses_cheapest_endpoint(monkeypatch, tmp_path, no_backfill):
    """effective_price_1m must reflect the cheapest real endpoint's own pricing,
    not just the bulk catalog headline -- the whole point of provider-routable pricing."""

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},  # headline: $2/$10 per 1M
        },
    })

    def fake_endpoints(canonical_slug, timeout=10.0):
        return [
            {  # expensive Azure endpoint
                "provider_name": "Azure",
                "pricing": {"prompt": "0.000005", "completion": "0.00003", "input_cache_read": "0.0000005"},
                "provider_info": {"dataPolicy": {"retainsPrompts": False}},
            },
            {  # cheaper direct OpenAI endpoint
                "provider_name": "OpenAI",
                "pricing": {"prompt": "0.000001", "completion": "0.000005", "input_cache_read": "0.0000001"},
                "provider_info": {"dataPolicy": {"retainsPrompts": True}},
            },
        ]

    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", fake_endpoints)

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    result = run_tracker(dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True)

    assert len(result.prices_shortlist) == 1
    model_price = result.prices_shortlist[0]
    # Cheaper OpenAI endpoint should win over the pricier Azure one and over
    # the bulk catalog's own headline (which is between the two).
    assert model_price.price.effective_price_1m < 5.0
    assert model_price.price.advertised_prompt_1m == pytest.approx(2.0, abs=1e-6)


def test_run_tracker_zdr_only_unroutable_emits_warning(monkeypatch, tmp_path, no_backfill):
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })
    # Every endpoint retains prompts -- fully ZDR-unroutable.
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [
        {
            "provider_name": "OpenAI",
            "pricing": {"prompt": "0.000001", "completion": "0.000005"},
            "provider_info": {"dataPolicy": {"retainsPrompts": True}},
        },
    ])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True, zdr_only=True
    )

    assert any(w.type == "POLICY_UNROUTABLE" for w in result.price_warnings)
    model_price = result.prices_shortlist[0]
    assert model_price.price.is_policy_routable is False
    assert model_price.price.policy_price_1m is None


def test_run_tracker_zdr_only_routable_uses_policy_price(monkeypatch, tmp_path, no_backfill):
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [
        {
            "provider_name": "OpenAI",
            "pricing": {"prompt": "0.000001", "completion": "0.000005"},
            "provider_info": {"dataPolicy": {"retainsPrompts": True}},  # not ZDR
        },
        {
            "provider_name": "Azure",
            "pricing": {"prompt": "0.000005", "completion": "0.00003"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},  # ZDR-compliant
        },
    ])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True, zdr_only=True
    )

    assert not any(w.type == "POLICY_UNROUTABLE" for w in result.price_warnings)
    model_price = result.prices_shortlist[0]
    assert model_price.price.is_policy_routable is True
    assert model_price.price.policy_price_1m is not None
    # Under an active ZDR filter, the display/sort price is policy-constrained,
    # which must be at least as expensive as the unconstrained effective price
    # here (the only ZDR-compliant endpoint is the pricier Azure one).
    assert model_price.price_1m == pytest.approx(model_price.price.policy_price_1m)
    assert model_price.price.policy_price_1m > model_price.price.effective_price_1m


def test_run_tracker_endpoint_route_failure_falls_back_to_bulk_catalog(monkeypatch, tmp_path, no_backfill):
    """Graceful degradation: if the internal per-endpoint route fails entirely,
    fall back to the bulk catalog's own pricing rather than crashing."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-luna": {
            "id": "openai/gpt-5.6-luna",
            "canonical_slug": "openai/gpt-5.6-luna-20260709",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012", "input_cache_read": "0.00000002"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-luna"])
    result = run_tracker(dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True)

    assert len(result.prices_shortlist) == 1
    assert result.prices_shortlist[0].price.effective_price_1m > 0


def test_run_tracker_same_day_rerun_does_not_shift_d1(monkeypatch, tmp_path):
    """Same-day-rerun bug fix (PLAN.md "Storage architecture"): running twice in
    one calendar day must not change d1, since d1..d30 are derived fresh from
    dated observations each time rather than shifted."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-luna": {
            "id": "openai/gpt-5.6-luna",
            "canonical_slug": "openai/gpt-5.6-luna-20260709",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {
        "inputChartData": [{"x": "2026-09-15 00:00:00", "y": {"ep1": 0.05}}],
        "outputChartData": [{"x": "2026-09-15 00:00:00", "y": {"ep1": 1.0}}],
    })

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-luna"])
    hist_path = tmp_path / "history.csv"

    fixed_now = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("anticharon.tracker.datetime", _FixedDatetime)

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)
    from anticharon.storage import read_history
    d1_after_first_run = read_history(hist_path)["openai/gpt-5.6-luna"].prices[0]

    # Second run, same calendar day.
    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)
    d1_after_second_run = read_history(hist_path)["openai/gpt-5.6-luna"].prices[0]

    assert d1_after_first_run == d1_after_second_run
