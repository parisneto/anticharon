"""Endpoint listed-price extraction and the live cross-validation canary against the
bulk catalog (PE2-005). The history source itself is covered by tests/test_listed_history.py.
"""

import pytest

from anticharon.tracker import (
    extract_endpoint_listed_prices_1m,
    fetch_endpoint_policy_pricing,
    fetch_openrouter_models,
)


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
