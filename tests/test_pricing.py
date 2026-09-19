"""Unit tests for anticharon.pricing's shared helpers (formula lives in test_golden_pricing.py).

Covers the negative-sentinel-price guard added after a real live finding:
`openrouter/auto-beta` (a meta-router model) lists `pricing.prompt`/`pricing.completion`
as the raw string "-1", which becomes a -1,000,000.0/1M sentinel once multiplied by
1,000,000 like every real price -- see tracker.py/discovery.py call sites.
"""

import pytest

from anticharon.pricing import (
    derive_cache_hit_rate,
    is_valid_listed_price,
    parse_required_price_1m,
    price_per_1m,
)


@pytest.mark.parametrize(
    "price_1m,expected",
    [
        (-1_000_000.0, False),  # openrouter/auto-beta's actual sentinel, post-conversion
        (-0.01, False),
        (0.0, True),  # genuine free/promo-tier model, not a sentinel
        (0.20, True),
        (30.0, True),
    ],
)
def test_is_valid_listed_price(price_1m, expected):
    assert is_valid_listed_price(price_1m) is expected


def test_price_per_1m_zero_tokens_does_not_divide_by_zero():
    assert price_per_1m(total_cost=0.0, total_tokens=0) == 0.0


# --- PE2-002: parse_required_price_1m must distinguish missing from genuine zero ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-002.


def test_parse_required_price_1m_missing_field_returns_none():
    """Missing key entirely -- e.g. an endpoint that omits `completion`."""
    assert parse_required_price_1m({"prompt": "0.000002"}, "completion") is None


def test_parse_required_price_1m_both_fields_missing_returns_none():
    assert parse_required_price_1m({}, "prompt") is None
    assert parse_required_price_1m({}, "completion") is None


def test_parse_required_price_1m_null_value_returns_none():
    assert parse_required_price_1m({"prompt": None}, "prompt") is None


def test_parse_required_price_1m_blank_string_returns_none():
    assert parse_required_price_1m({"prompt": ""}, "prompt") is None
    assert parse_required_price_1m({"prompt": "   "}, "prompt") is None


def test_parse_required_price_1m_malformed_value_returns_none():
    assert parse_required_price_1m({"prompt": "not-a-number"}, "prompt") is None
    assert parse_required_price_1m({"prompt": {}}, "prompt") is None


def test_parse_required_price_1m_legitimate_zero_is_valid():
    """A real free model lists "0" explicitly -- must parse as a real $0.0/1M,
    not be confused with a missing field."""
    assert parse_required_price_1m({"prompt": "0"}, "prompt") == 0.0
    assert parse_required_price_1m({"prompt": 0}, "prompt") == 0.0


def test_parse_required_price_1m_real_value_converts_to_per_1m():
    assert parse_required_price_1m({"prompt": "0.000002"}, "prompt") == pytest.approx(2.0)


# --- PE2-008: derive_cache_hit_rate must compute the real cache-hit rate ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-008.


def test_derive_cache_hit_rate_default_weights_round_trips_to_the_original_default():
    """The default weight_uncached_prompt/weight_cached_prompt in config.py were
    themselves derived FROM an interim default cache-hit-rate of 0.766701
    (PLAN.md "Core pricing semantics"). Deriving the rate back from those same
    weights must round-trip to that same number -- this is the strongest
    possible correctness check, since it's not just internally consistent,
    it recovers the exact independently-known original value."""
    rate = derive_cache_hit_rate(weight_uncached_prompt=0.232622, weight_cached_prompt=0.764478)
    assert rate == pytest.approx(0.766701, abs=1e-5)
    # The previous (buggy) behavior returned weight_cached_prompt directly --
    # confirm the fix actually changed the value, not just its label.
    assert rate != pytest.approx(0.764478, abs=1e-4)


def test_derive_cache_hit_rate_calibrated_weights_with_nonzero_completion_share():
    """Required regression test: 'Calibrated weights with nonzero completion
    share.' Uses real calibrated numbers from docs/sample/'s pooled cache-hit-rate
    (0.7667012846565789, from log_parser.py's own test coverage) with a
    realistic nonzero completion weight, confirming completion share does not
    leak into the derived rate (only prompt-side weights should matter)."""
    total_prompt_share = 0.99  # 1% completion
    cache_hit = 0.7667012846565789
    w_cached = total_prompt_share * cache_hit
    w_uncached = total_prompt_share * (1 - cache_hit)
    rate = derive_cache_hit_rate(w_uncached, w_cached)
    assert rate == pytest.approx(cache_hit, abs=1e-9)


def test_derive_cache_hit_rate_zero_cached_weight_is_zero():
    """Required regression test: 'Zero cached weight.' No cache activity at
    all -- the derived rate must be exactly 0.0, not undefined or fabricated."""
    assert derive_cache_hit_rate(weight_uncached_prompt=0.9971, weight_cached_prompt=0.0) == 0.0


def test_derive_cache_hit_rate_zero_total_prompt_weight_is_zero_not_division_error():
    """Required regression test: 'Zero total prompt weight.' A degenerate
    100%-completion mix (both prompt weights are 0) must return 0.0 -- the
    explicitly defined zero-prompt-weight behavior -- never raise ZeroDivisionError
    and never fabricate a nonzero rate."""
    assert derive_cache_hit_rate(weight_uncached_prompt=0.0, weight_cached_prompt=0.0) == 0.0
