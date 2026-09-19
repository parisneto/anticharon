"""Tests for anticharon.tracker.resolve_policy_pricing: the real, unauthenticated
ZDR signal (`provider_info.dataPolicy.retainsPrompts`) from the internal
`/api/frontend/v1/stats/endpoint` route (PLAN.md "Policy (ZDR) pricing data
source"). Fixture-based, no network -- `openrouter_endpoint_stats_gpt-5.6-luna_trimmed.json`
is a real live-captured response, trimmed to the fields this module consumes.
"""

import json
from pathlib import Path

import pytest

from anticharon.tracker import resolve_policy_pricing

FIXTURES_DIR = Path(__file__).parent / "fixtures"

W_UNCACHED, W_CACHED, W_COMPLETION = 0.232622, 0.764478, 0.0029


def _load_fixture(name: str):
    with open(FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)["data"]


def test_resolve_policy_pricing_mixed_endpoints_real_fixture():
    """Real live-captured mix: some endpoints ZDR-compliant (Azure, Bedrock),
    some not (direct OpenAI variants)."""
    endpoints = _load_fixture("openrouter_endpoint_stats_gpt-5.6-luna_trimmed.json")

    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)

    assert result["effective_price_1m"] is not None
    assert result["is_policy_routable"] is True
    assert result["policy_price_1m"] is not None
    # The ZDR-compliant endpoints (Azure/Bedrock) are all pricier than the
    # cheapest overall (OpenAI flex) -- policy price must reflect that.
    assert result["policy_price_1m"] >= result["effective_price_1m"]
    # Non-compliant providers (retainsPrompts=true) must be listed as excluded.
    assert "OpenAI" in result["excluded_providers"]


def test_resolve_policy_pricing_zdr_inactive_skips_policy_computation():
    endpoints = _load_fixture("openrouter_endpoint_stats_gpt-5.6-luna_trimmed.json")
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=False)
    assert result["effective_price_1m"] is not None
    assert result["policy_price_1m"] is None
    assert result["is_policy_routable"] is None
    assert result["excluded_providers"] == []


def test_resolve_policy_pricing_fully_unroutable_under_zdr():
    """Required per PLAN.md's Testing section: a fixture case where every
    endpoint retains prompts -- the correct behavior is fully unroutable, not
    an error and not a fabricated policy price."""
    endpoints = [
        {
            "provider_name": "OpenAI",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
            "provider_info": {"dataPolicy": {"retainsPrompts": True}},
        },
        {
            "provider_name": "OpenAI Fast",
            "pricing": {"prompt": "0.000004", "completion": "0.00002"},
            "provider_info": {"dataPolicy": {"retainsPrompts": True}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)

    assert result["effective_price_1m"] is not None  # unconstrained price still resolves
    assert result["is_policy_routable"] is False
    assert result["policy_price_1m"] is None
    assert set(result["excluded_providers"]) == {"OpenAI", "OpenAI Fast"}


def test_resolve_policy_pricing_no_endpoints_is_unknown_not_unroutable():
    """Graceful degradation: no endpoint data at all (route failed) means
    policy-routability is *unknown*, not a fabricated ZDR-unroutable warning."""
    result = resolve_policy_pricing([], W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] is None
    assert result["is_policy_routable"] is None
    assert result["policy_price_1m"] is None


def test_resolve_policy_pricing_skips_sentinel_priced_endpoint():
    endpoints = [
        {
            "provider_name": "openrouter-meta",
            "pricing": {"prompt": "-1", "completion": "-1"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
        {
            "provider_name": "OpenAI",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] == pytest.approx(
        result["policy_price_1m"]
    )  # only the valid endpoint contributes


# --- PE2-002: missing/partial required pricing must never become a fabricated $0 ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-002.


def test_resolve_policy_pricing_endpoint_with_empty_pricing_dict_is_skipped():
    """Exact evidence scenario from PE2-002: an endpoint with `pricing={}` must
    never resolve to effective_price_1m=0.0/policy_price_1m=0.0/is_policy_routable=true."""
    endpoints = [
        {
            "provider_name": "broken-provider",
            "pricing": {},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] is None
    assert result["policy_price_1m"] is None
    assert result["is_policy_routable"] is None  # no usable endpoints at all -- unknown, not routable


def test_resolve_policy_pricing_endpoint_missing_completion_field_is_skipped():
    endpoints = [
        {
            "provider_name": "partial-provider",
            "pricing": {"prompt": "0.000002"},  # completion entirely absent
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] is None


def test_resolve_policy_pricing_endpoint_blank_prompt_is_skipped():
    endpoints = [
        {
            "provider_name": "blank-provider",
            "pricing": {"prompt": "", "completion": "0.00001"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] is None


def test_resolve_policy_pricing_mixed_valid_and_malformed_endpoints_uses_only_valid():
    """A mix of one endpoint with missing pricing and one real endpoint --
    the malformed one must be silently excluded, not treated as a free $0 winner."""
    endpoints = [
        {
            "provider_name": "broken-provider",
            "pricing": {},  # would incorrectly win as "cheapest" if defaulted to $0
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
        {
            "provider_name": "OpenAI",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] is not None
    assert result["effective_price_1m"] > 0  # never the fabricated $0 from the broken endpoint
    assert "broken-provider" not in result["excluded_providers"]  # never counted as a real candidate at all


def test_resolve_policy_pricing_all_endpoints_malformed_returns_none():
    endpoints = [
        {"provider_name": "a", "pricing": {}, "provider_info": {"dataPolicy": {"retainsPrompts": False}}},
        {"provider_name": "b", "pricing": {"prompt": "garbage", "completion": "0.00001"},
         "provider_info": {"dataPolicy": {"retainsPrompts": False}}},
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] is None
    assert result["policy_price_1m"] is None
    assert result["is_policy_routable"] is None


def test_resolve_policy_pricing_legitimate_zero_endpoint_is_used():
    """A genuinely free endpoint (explicit "0", not missing) must still be usable."""
    endpoints = [
        {
            "provider_name": "free-provider",
            "pricing": {"prompt": "0", "completion": "0"},
            "provider_info": {"dataPolicy": {"retainsPrompts": False}},
        },
    ]
    result = resolve_policy_pricing(endpoints, W_UNCACHED, W_CACHED, W_COMPLETION, zdr_only=True)
    assert result["effective_price_1m"] == 0.0
    assert result["is_policy_routable"] is True
