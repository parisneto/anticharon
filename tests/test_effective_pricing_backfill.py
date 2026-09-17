"""Tests for the 28-day backfill path: `range=1m` on the internal effective-pricing
route (PLAN.md "28-Day Backfill" -- live-verified the bare/default call only
returns 8 days), the daily-observation reduction, and graceful degradation.
The cross-validation canary against the live API is @pytest.mark.live.
"""

import pytest

from anticharon.tracker import (
    _reduce_to_daily_observations,
    fetch_effective_pricing_history,
    fetch_openrouter_models,
    sync_effective_prices_for_model,
)


def test_reduce_to_daily_observations_picks_cheapest_endpoint_per_day():
    history_data = {
        "inputChartData": [
            {"x": "2026-09-15 00:00:00", "y": {"ep1": 0.10, "ep2": 0.05}},
            {"x": "2026-09-16 00:00:00", "y": {"ep1": 0.08}},
        ],
        "outputChartData": [
            {"x": "2026-09-15 00:00:00", "y": {"ep1": 1.0, "ep2": 2.0}},
            {"x": "2026-09-16 00:00:00", "y": {"ep1": 1.0}},
        ],
    }
    observations = _reduce_to_daily_observations(history_data, w_completion=0.0029)

    assert len(observations) == 2
    by_date = {o["date"]: o["effective_price_1m"] for o in observations}
    # 2026-09-15: ep1 = 0.10*(1-0.0029) + 1.0*0.0029; ep2 = 0.05*(1-0.0029) + 2.0*0.0029
    ep1 = 0.10 * (1 - 0.0029) + 1.0 * 0.0029
    ep2 = 0.05 * (1 - 0.0029) + 2.0 * 0.0029
    assert by_date["2026-09-15"] == pytest.approx(min(ep1, ep2))


def test_reduce_to_daily_observations_skips_endpoint_missing_output_side():
    history_data = {
        "inputChartData": [{"x": "2026-09-15 00:00:00", "y": {"ep1": 0.10, "ep_no_output": 0.02}}],
        "outputChartData": [{"x": "2026-09-15 00:00:00", "y": {"ep1": 1.0}}],
    }
    observations = _reduce_to_daily_observations(history_data, w_completion=0.0029)
    assert len(observations) == 1


def test_reduce_to_daily_observations_empty_input_is_empty():
    assert _reduce_to_daily_observations({}, w_completion=0.0029) == []
    assert _reduce_to_daily_observations({"inputChartData": [], "outputChartData": []}, w_completion=0.0029) == []


def test_reduce_to_daily_observations_provider_identity_is_intentionally_discarded():
    """PE2-004: this is an approved reduction rule, not an oversight -- see the
    "Scope correction" note in docs/plans/pricing-engine-v2/PLAN.md's Storage
    architecture section. Given multiple providers/endpoints on the same day,
    the stored observation must be exactly {date, effective_price_1m} -- no
    provider identifier, listed price, cache-hit rate, or token share key.
    This test exists to make a future accidental re-introduction of
    provider-level fields (or accidental loss of the cheapest-of-day
    reduction) fail loudly, since it locks in the exact current shape."""
    history_data = {
        "inputChartData": [
            {"x": "2026-09-15 00:00:00", "y": {"openai-ep": 0.10, "azure-ep": 0.05, "bedrock-ep": 0.20}},
        ],
        "outputChartData": [
            {"x": "2026-09-15 00:00:00", "y": {"openai-ep": 1.0, "azure-ep": 2.0, "bedrock-ep": 3.0}},
        ],
    }
    observations = _reduce_to_daily_observations(history_data, w_completion=0.0029)

    assert len(observations) == 1
    assert set(observations[0].keys()) == {"date", "effective_price_1m"}
    # The cheapest endpoint (azure-ep) must win -- provider identity is used
    # only transiently during this reduction, never persisted.
    azure_rate = 0.05 * (1 - 0.0029) + 2.0 * 0.0029
    assert observations[0]["effective_price_1m"] == pytest.approx(azure_rate)


def test_sync_effective_prices_for_model_graceful_degradation_on_empty_fetch(monkeypatch):
    """A `~`-prefixed router alias (e.g. `~deepseek/deepseek-pro-latest`) returns
    an empty-but-200-OK payload (live-verified: no fixed permaslug identity to
    have history against). Must not fabricate observations or crash."""
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})

    store = {}
    sync_effective_prices_for_model("~deepseek/deepseek-pro-latest", "~deepseek/deepseek-pro-latest", store, 0.0029, timeout=10.0)

    assert store["~deepseek/deepseek-pro-latest"]["observations"] == []
    assert store["~deepseek/deepseek-pro-latest"]["first_seen"] is not None


def test_sync_effective_prices_for_model_preserves_prior_data_on_transient_failure(monkeypatch):
    """A transient failure on a later sync must not destroy previously
    accumulated real observations."""
    store = {
        "openai/gpt-5.6-luna": {
            "canonical_slug": "openai/gpt-5.6-luna-20260709",
            "first_seen": "2026-08-01",
            "last_synced": "2026-08-01T00:00:00+00:00",  # stale -- will attempt refresh
            "observations": [{"date": "2026-08-01", "effective_price_1m": 0.05}],
        }
    }
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})

    sync_effective_prices_for_model(
        "openai/gpt-5.6-luna", "openai/gpt-5.6-luna-20260709", store, 0.0029, timeout=10.0
    )

    assert store["openai/gpt-5.6-luna"]["observations"] == [{"date": "2026-08-01", "effective_price_1m": 0.05}]


@pytest.mark.live
def test_effective_pricing_range_1m_returns_at_least_28_days():
    """Live contract check: the bare/default call only returns ~8 days -- the
    28-day backfill requires the `range=1m` param explicitly (live-verified
    2026-09-16, not documented anywhere public)."""
    models_api = fetch_openrouter_models()
    assert models_api, "bulk catalog fetch failed -- cannot run this live contract test"
    api_data = models_api.get("openai/gpt-5.6-luna")
    assert api_data is not None
    canonical_slug = api_data.get("canonical_slug") or "openai/gpt-5.6-luna"

    history_data = fetch_effective_pricing_history(canonical_slug)
    assert len(history_data.get("inputChartData", [])) >= 28


@pytest.mark.live
def test_effective_pricing_cross_validation_canary():
    """Canary: the cheapest endpoint's most recent effective input price should
    not exceed the bulk catalog's advertised listed prompt price by more than a
    reasonable margin -- caching only ever discounts, it doesn't mark up. If
    this diverges wildly, one of the two routes likely changed shape/semantics."""
    models_api = fetch_openrouter_models()
    assert models_api, "bulk catalog fetch failed -- cannot run this live contract test"
    api_data = models_api.get("openai/gpt-5.6-luna")
    assert api_data is not None
    canonical_slug = api_data.get("canonical_slug") or "openai/gpt-5.6-luna"
    advertised_prompt_1m = float(api_data["pricing"]["prompt"]) * 1_000_000

    history_data = fetch_effective_pricing_history(canonical_slug)
    input_series = history_data.get("inputChartData", [])
    assert input_series, "effective-pricing route returned no data for a known-tracked model"

    latest_day = input_series[-1]
    cheapest_effective_input = min(latest_day.get("y", {}).values())
    assert cheapest_effective_input <= advertised_prompt_1m * 1.5
