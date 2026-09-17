"""Unit tests for anticharon.pricing's shared helpers (formula lives in test_golden_pricing.py).

Covers the negative-sentinel-price guard added after a real live finding:
`openrouter/auto-beta` (a meta-router model) lists `pricing.prompt`/`pricing.completion`
as the raw string "-1", which becomes a -1,000,000.0/1M sentinel once multiplied by
1,000,000 like every real price -- see tracker.py/discovery.py call sites.
"""

import pytest

from anticharon.pricing import is_valid_listed_price, parse_required_price_1m, price_per_1m


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
