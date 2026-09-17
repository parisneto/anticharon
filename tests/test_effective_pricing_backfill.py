"""Tests for the 28-day backfill path: `range=1m` on the internal effective-pricing
route (PLAN.md "28-Day Backfill" -- live-verified the bare/default call only
returns 8 days), the daily-observation reduction, and graceful degradation.
The cross-validation canary against the live API is @pytest.mark.live.
"""

import pytest

from anticharon.tracker import (
    _reduce_to_daily_observations,
    extract_endpoint_listed_prices_1m,
    fetch_effective_pricing_history,
    fetch_endpoint_policy_pricing,
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


# --- PE2-005: the cross-validation canary must compare like-for-like listed prices ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-005.


def test_extract_endpoint_listed_prices_1m_basic():
    endpoints = [
        {"provider_name": "OpenAI", "pricing": {"prompt": "0.0000002", "completion": "0.0000012"}},
        {"provider_name": "Azure", "pricing": {"prompt": "0.00000022", "completion": "0.00000132"}},
    ]
    prices = extract_endpoint_listed_prices_1m(endpoints)
    assert prices == pytest.approx([0.2, 0.22])


def test_extract_endpoint_listed_prices_1m_missing_listed_baseline_returns_empty():
    """PE2-005's required 'missing listed baseline' case: every endpoint has
    malformed/missing pricing -- extraction must return [] gracefully, not crash."""
    endpoints = [
        {"provider_name": "broken-1", "pricing": {}},
        {"provider_name": "broken-2", "pricing": {"prompt": "not-a-number", "completion": "0.00001"}},
    ]
    assert extract_endpoint_listed_prices_1m(endpoints) == []


def test_extract_endpoint_listed_prices_1m_skips_sentinel_prices():
    """PE2-005's required 'changed payload shape' case, applied to a real
    shape variant already seen live: a meta-router endpoint reporting the
    "-1" sentinel must not be extracted as a real listed price."""
    endpoints = [
        {"provider_name": "meta-router", "pricing": {"prompt": "-1", "completion": "-1"}},
        {"provider_name": "OpenAI", "pricing": {"prompt": "0.0000002", "completion": "0.0000012"}},
    ]
    assert extract_endpoint_listed_prices_1m(endpoints) == pytest.approx([0.2])


@pytest.mark.live
def test_effective_pricing_cross_validation_canary():
    """Corrected 2026-09-17 (PE2-005): the original design assumed the internal
    effective-pricing route (`/stats/effective-pricing`) exposes a distinct
    "listed" baseline to compare against the bulk catalog's advertised price.
    Live-verified 2026-09-17 that it does not -- its payload only ever
    contains cache-weighted `effectiveInputPrice`/`effectiveOutputPrice` per
    provider and aggregate `weightedInputPrice`/`weightedOutputPrice`; there
    is no raw listed-price field anywhere in it to extract.

    The real, available cross-validation signal instead: the bulk catalog's
    `advertised_prompt_1m` is definitionally one of the real routable
    endpoints' own listed price (OpenRouter's headline is never a fabricated
    number) -- from `/stats/endpoint`, the same route `fetch_endpoint_policy_pricing`
    already uses elsewhere in this codebase. Live-verified 2026-09-17 for
    `openai/gpt-5.6-luna`: two of seven endpoints report exactly the
    advertised price. Tolerance is a tight float-rounding allowance
    (`abs(diff) < 1e-6`), not a loose multiplier, since these are the same
    underlying number when the pairing holds -- a loose tolerance (the
    previous "<= 1.5x" check) can pass even when the routes have drifted
    apart semantically, which is exactly what this canary exists to catch."""
    models_api = fetch_openrouter_models()
    assert models_api, "bulk catalog fetch failed -- cannot run this live contract test"
    api_data = models_api.get("openai/gpt-5.6-luna")
    assert api_data is not None
    canonical_slug = api_data.get("canonical_slug") or "openai/gpt-5.6-luna"
    advertised_prompt_1m = float(api_data["pricing"]["prompt"]) * 1_000_000

    endpoints = fetch_endpoint_policy_pricing(canonical_slug)
    assert endpoints, "endpoint route returned no data for a known-tracked model"

    listed_prices = extract_endpoint_listed_prices_1m(endpoints)
    assert listed_prices, "no endpoint reported a usable listed price -- possible schema/semantics drift"

    matches = [p for p in listed_prices if abs(p - advertised_prompt_1m) < 1e-6]
    assert matches, (
        f"bulk catalog advertised price {advertised_prompt_1m} matched none of the "
        f"endpoint listed prices {listed_prices} -- possible schema/semantics drift "
        f"between the bulk catalog and /stats/endpoint"
    )
