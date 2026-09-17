"""Tests for anticharon.tracker: the cache-aware, provider-routable pricing
engine (docs/plans/pricing-engine-v2/PLAN.md). All network calls are mocked --
`@pytest.mark.live` tests for the real API contracts live in
test_effective_pricing_backfill.py and test_policy_pricing.py.
"""

import json
from datetime import datetime, timedelta, timezone

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
    # PE2-001 fix (corrected 2026-09-16): price_1m is ALWAYS the unconstrained
    # effective price, never replaced by the policy price -- even under an
    # active ZDR filter. This assertion previously encoded the opposite
    # (price_1m == policy_price_1m), which was RELEASE_VALIDATION.md#PE2-001's
    # exact defect ("ZDR output mislabeled policy price as effective").
    # Policy-aware ranking for sort/BEST_OPTION_CHANGED is computed separately
    # in run_tracker from price.policy_price_1m, not by mutating price_1m.
    assert model_price.price_1m == pytest.approx(model_price.price.effective_price_1m)
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


# --- PE2-001 regression tests: effective and policy prices collapse under ZDR ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001.


def test_run_tracker_zdr_effective_price_field_not_collapsed_with_policy(monkeypatch, tmp_path, no_backfill):
    """PE2-001 evidence #1: the serialized `effective_price_1m` field (what CLI
    --json / the check_prices MCP tool actually return) must report the true
    unconstrained effective price, never the policy-constrained price, even
    when they differ substantially under an active policy filter."""
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
            "provider_info": {"dataPolicy": {"retainsPrompts": True}},  # not ZDR -- cheap
        },
        {
            "provider_name": "Azure",
            "pricing": {"prompt": "0.000005", "completion": "0.00003"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},  # ZDR-compliant -- expensive
        },
    ])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True, zdr_only=True
    )
    model_price = result.prices_shortlist[0]
    assert model_price.price.policy_price_1m > model_price.price.effective_price_1m  # sanity: they really differ

    serialized = model_price.to_dict()
    assert serialized["effective_price_1m"] == pytest.approx(model_price.price.effective_price_1m, abs=1e-5)
    assert serialized["effective_price_1m"] != pytest.approx(model_price.price.policy_price_1m, abs=1e-3)
    assert serialized["policy_price_1m"] == pytest.approx(model_price.price.policy_price_1m, abs=1e-5)


def test_run_tracker_zdr_never_recommends_unroutable_model_as_best_option(monkeypatch, tmp_path, no_backfill):
    """PE2-001 evidence #2: a model with NO ZDR-compliant endpoint at all must
    never be ranked first or recommended via BEST_OPTION_CHANGED under an
    active policy filter, even if its unconstrained effective price is the
    cheapest in the whole shortlist. Reproduces the exact scenario from
    RELEASE_VALIDATION.md#PE2-001 ("Unroutable Qwen model was recommended as
    BEST_OPTION_CHANGED")."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "provider/expensive-default": {
            "id": "provider/expensive-default", "canonical_slug": "provider/expensive-default",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
        "provider/cheap-routable": {
            "id": "provider/cheap-routable", "canonical_slug": "provider/cheap-routable",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
        "provider/cheap-unroutable": {
            "id": "provider/cheap-unroutable", "canonical_slug": "provider/cheap-unroutable",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })

    def fake_endpoints(canonical_slug, timeout=10.0):
        if canonical_slug == "provider/expensive-default":
            return [{  # ZDR-compliant, expensive
                "provider_name": "Azure",
                "pricing": {"prompt": "0.000005", "completion": "0.00003"},
                "provider_info": {"dataPolicy": {"retainsPrompts": False}},
            }]
        if canonical_slug == "provider/cheap-routable":
            return [
                {  # ZDR-compliant, moderate -- this is the actual policy-cheapest option
                    "provider_name": "Azure",
                    "pricing": {"prompt": "0.000001", "completion": "0.000005"},
                    "provider_info": {"dataPolicy": {"retainsPrompts": False}},
                },
                {  # non-ZDR, cheaper but irrelevant to policy ranking
                    "provider_name": "OpenAI",
                    "pricing": {"prompt": "0.0000005", "completion": "0.0000025"},
                    "provider_info": {"dataPolicy": {"retainsPrompts": True}},
                },
            ]
        if canonical_slug == "provider/cheap-unroutable":
            return [{  # only endpoint retains prompts -- fully unroutable under ZDR,
                       # but the cheapest unconstrained effective price of all three
                "provider_name": "OpenAI",
                "pricing": {"prompt": "0.0000001", "completion": "0.0000005"},
                "provider_info": {"dataPolicy": {"retainsPrompts": True}},
            }]
        return []

    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", fake_endpoints)

    cfg_path = _write_shortlist(tmp_path, [
        "provider/expensive-default", "provider/cheap-routable", "provider/cheap-unroutable"
    ])
    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True, zdr_only=True
    )

    # Sanity: the unroutable model really does have the cheapest unconstrained
    # effective price -- otherwise this test wouldn't distinguish old vs new behavior.
    by_model = {p.model: p for p in result.prices_shortlist}
    assert by_model["provider/cheap-unroutable"].price.effective_price_1m < by_model["provider/cheap-routable"].price.effective_price_1m

    model_ids_in_order = [p.model for p in result.prices_shortlist]
    assert model_ids_in_order[0] != "provider/cheap-unroutable"
    assert model_ids_in_order[0] == "provider/cheap-routable"

    best_option_warnings = [w for w in result.price_warnings if w.type == "BEST_OPTION_CHANGED"]
    assert len(best_option_warnings) == 1
    assert best_option_warnings[0].suggested_cheapest == "provider/cheap-routable"
    assert best_option_warnings[0].suggested_cheapest != "provider/cheap-unroutable"


def test_run_tracker_zdr_delta_compares_effective_not_policy_price(monkeypatch, tmp_path):
    """PE2-001 evidence #3 ("Compare like-for-like current and historical
    prices"): delta_7d_pct (and PRICE_SPIKE/PRICE_DROP) must compare the
    unconstrained effective price against ma_7d, never the policy price --
    ma_7d/ma_3d are always derived from unconstrained effective observations
    in effective_prices.json, so mixing a policy-constrained *current* price
    with an unconstrained *historical* average would be an apples-to-oranges
    comparison."""
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
            "pricing": {"prompt": "0.000001", "completion": "0.000005", "input_cache_read": "0.0000001"},
            "provider_info": {"dataPolicy": {"retainsPrompts": True}},  # not ZDR -- cheapest overall
        },
        {
            "provider_name": "Azure",
            "pricing": {"prompt": "0.000005", "completion": "0.00003", "input_cache_read": "0.0000005"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},  # ZDR-compliant -- pricier
        },
    ])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    hist_path = tmp_path / "history.csv"
    effective_prices_path = tmp_path / "effective_prices.json"

    fixed_now = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
    known_ma_price = 0.5
    seeded_observations = [
        {"date": (fixed_now.date() - timedelta(days=n)).isoformat(), "effective_price_1m": known_ma_price}
        for n in range(1, 8)
    ]
    effective_prices_path.write_text(json.dumps({
        "openai/gpt-5.6-sol": {
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "first_seen": "2026-08-01",
            "last_synced": fixed_now.isoformat(),  # fresh -- backfill fetch must not run
            "observations": seeded_observations,
        }
    }), encoding="utf-8")

    def _fail_if_called(*a, **kw):
        raise AssertionError("fetch_effective_pricing_history must not be called -- store entry is fresh")

    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", _fail_if_called)

    class _FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now

    monkeypatch.setattr("anticharon.tracker.datetime", _FixedDatetime)

    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=hist_path, no_hermes=True, zdr_only=True
    )

    model_price = result.prices_shortlist[0]
    effective = model_price.price.effective_price_1m
    policy = model_price.price.policy_price_1m
    assert policy is not None and policy != pytest.approx(effective)  # sanity: they really differ

    assert model_price.ma_7d == pytest.approx(known_ma_price)
    expected_delta = ((effective - known_ma_price) / known_ma_price) * 100
    wrong_delta_if_using_policy = ((policy - known_ma_price) / known_ma_price) * 100
    assert model_price.change_vs_7d_pct == pytest.approx(expected_delta, abs=1e-4)
    assert model_price.change_vs_7d_pct != pytest.approx(wrong_delta_if_using_policy, abs=1e-4)


# --- PE2-002: missing/partial bulk-catalog pricing must never become a fabricated $0 ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-002.


def test_run_tracker_skips_model_with_missing_bulk_catalog_completion_field(monkeypatch, tmp_path, no_backfill):
    """A shortlisted model whose bulk-catalog entry is missing `pricing.completion`
    entirely must be excluded from the run, never priced at a fabricated $0 output."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-luna": {
            "id": "openai/gpt-5.6-luna",
            "canonical_slug": "openai/gpt-5.6-luna-20260709",
            "pricing": {"prompt": "0.0000002"},  # completion field entirely absent
        },
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-luna", "openai/gpt-5.6-sol"])
    result = run_tracker(dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True)

    model_ids = [p.model for p in result.prices_shortlist]
    assert "openai/gpt-5.6-luna" not in model_ids
    assert "openai/gpt-5.6-sol" in model_ids


def test_run_tracker_endpoint_with_empty_pricing_does_not_win_cheapest(monkeypatch, tmp_path, no_backfill):
    """PE2-002 exact evidence scenario reproduced end-to-end through run_tracker:
    a per-endpoint entry with pricing={} must never resolve to the cheapest
    ($0.0) effective price and win BEST_OPTION_CHANGED over a real, priced model."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [
        {"provider_name": "broken", "pricing": {}, "provider_info": {"dataPolicy": {"retainsPrompts": False}}},
    ])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    result = run_tracker(dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True)

    model_price = result.prices_shortlist[0]
    # With the broken endpoint excluded, effective_price_1m must fall back to
    # the bulk catalog's own (real, non-zero) headline pricing, never $0.0.
    assert model_price.price.effective_price_1m > 0


# --- PE2-003: policy-unknown must be distinct from confirmed-unroutable ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-003. Also reconciles
# PE2-001's independent-retest flag: policy-unknown and confirmed-unroutable must
# NOT share the same (math.inf) ranking outcome.


def test_run_tracker_zdr_policy_unknown_emits_policy_unknown_not_unroutable_warning(
    monkeypatch, tmp_path, no_backfill
):
    """When the endpoint route returns no usable data at all, run_tracker must
    surface POLICY_UNKNOWN, never POLICY_UNROUTABLE (that warning is reserved
    for confirmed noncompliance, where real endpoint data was checked)."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-sol"])
    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True, zdr_only=True
    )

    warning_types = [w.type for w in result.price_warnings]
    assert "POLICY_UNKNOWN" in warning_types
    assert "POLICY_UNROUTABLE" not in warning_types

    model_price = result.prices_shortlist[0]
    assert model_price.price.is_policy_routable is None
    assert model_price.price.policy_price_1m is None


def test_run_tracker_zdr_policy_unknown_model_can_still_be_recommended(monkeypatch, tmp_path, no_backfill):
    """Reconciles PE2-001's independent-retest flag directly: a policy-unknown
    model (routable-by-default) must rank by its unconstrained effective price
    and CAN win BEST_OPTION_CHANGED -- unlike a confirmed-unroutable model,
    which must never win it (see test_run_tracker_zdr_never_recommends_
    unroutable_model_as_best_option above, still passing)."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "provider/expensive-default": {
            "id": "provider/expensive-default", "canonical_slug": "provider/expensive-default",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
        "provider/cheap-unknown": {
            "id": "provider/cheap-unknown", "canonical_slug": "provider/cheap-unknown",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000005"},
        },
    })

    def fake_endpoints(canonical_slug, timeout=10.0):
        if canonical_slug == "provider/expensive-default":
            return [{
                "provider_name": "Azure",
                "pricing": {"prompt": "0.000005", "completion": "0.00003"},
                "provider_info": {"dataPolicy": {"retainsPrompts": False}},
            }]
        return []  # provider/cheap-unknown: no endpoint data at all -- policy-unknown

    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", fake_endpoints)

    cfg_path = _write_shortlist(tmp_path, ["provider/expensive-default", "provider/cheap-unknown"])
    result = run_tracker(
        dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True, zdr_only=True
    )

    by_model = {p.model: p for p in result.prices_shortlist}
    assert by_model["provider/cheap-unknown"].price.is_policy_routable is None

    # The unknown model ranks first (by its unconstrained effective price, the
    # routable-by-default fallback) and IS eligible to be recommended.
    model_ids_in_order = [p.model for p in result.prices_shortlist]
    assert model_ids_in_order[0] == "provider/cheap-unknown"

    best_option_warnings = [w for w in result.price_warnings if w.type == "BEST_OPTION_CHANGED"]
    assert len(best_option_warnings) == 1
    assert best_option_warnings[0].suggested_cheapest == "provider/cheap-unknown"

    policy_unknown_warnings = [w for w in result.price_warnings if w.type == "POLICY_UNKNOWN"]
    assert len(policy_unknown_warnings) == 1
    assert policy_unknown_warnings[0].model == "provider/cheap-unknown"


# --- PE2-008: cache_hit_rate_used must be the real cache-hit rate, not weight_cached_prompt ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-008.


def test_run_tracker_cache_hit_rate_used_is_the_real_rate_not_the_raw_weight(monkeypatch, tmp_path, no_backfill):
    """End-to-end: the default weight_uncached_prompt/weight_cached_prompt in
    config.py were derived FROM an interim default cache-hit-rate of 0.766701
    (PLAN.md "Core pricing semantics") -- PricePoint.cache_hit_rate_used must
    round-trip back to that same number, not report weight_cached_prompt
    (0.764478) directly, which is a materially different value."""
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-luna": {
            "id": "openai/gpt-5.6-luna",
            "canonical_slug": "openai/gpt-5.6-luna-20260709",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])

    cfg_path = _write_shortlist(tmp_path, ["openai/gpt-5.6-luna"])
    result = run_tracker(dry_run=True, config_path=cfg_path, history_path=tmp_path / "history.csv", no_hermes=True)

    model_price = result.prices_shortlist[0]
    assert model_price.price.cache_hit_rate_used == pytest.approx(0.766701, abs=1e-5)
    assert model_price.price.cache_hit_rate_used != pytest.approx(0.764478, abs=1e-4)
