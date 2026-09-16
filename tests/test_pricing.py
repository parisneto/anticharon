"""Unit tests for anticharon.pricing's shared helpers (formula lives in test_golden_pricing.py).

Covers the negative-sentinel-price guard added after a real live finding:
`openrouter/auto-beta` (a meta-router model) lists `pricing.prompt`/`pricing.completion`
as the raw string "-1", which becomes a -1,000,000.0/1M sentinel once multiplied by
1,000,000 like every real price -- see tracker.py/discovery.py call sites.
"""

import pytest

from anticharon.pricing import is_valid_listed_price, price_per_1m


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
