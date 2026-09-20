"""Tests for anticharon.chart: ASCII price spectrum rendering (unchanged by
the pricing-engine-v2 rework -- ModelPrice.price_1m stays the sort/chart key)."""

import math
import re

from anticharon.chart import render_ascii_price_bar
from anticharon.models import ModelPrice, PricePoint


def _bar_widths(lines):
    """Bar block-count per rendered model row, in render order."""
    widths = []
    for line in lines:
        m = re.search(r"(█+)", line)
        if m:
            widths.append(len(m.group(1)))
    return widths


def test_ascii_chart_renders_expected_sections():
    sample_prices = [
        ModelPrice(model="qwen/qwen3.7-flash", price_1m=0.03029, ma_7d=0.03029, ma_3d=0.03029, change_vs_7d_pct=0.0),
        ModelPrice(model="openai/gpt-5.6-luna", price_1m=0.20294, ma_7d=0.20294, ma_3d=0.20294, change_vs_7d_pct=0.0),
        ModelPrice(model="google/gemini-3.7-flash", price_1m=0.37941, ma_7d=0.37941, ma_3d=0.37941, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(sample_prices, default_model="openai/gpt-5.6-luna")
    assert len(lines) >= 5
    assert any("▲ Cheaper" in l for l in lines)
    assert any("▼ More Expensive" in l for l in lines)
    assert any("🏆 [BEST]" in l for l in lines)
    assert any("★ [DEFAULT]" in l for l in lines)


def test_ascii_chart_correct_under_zdr_policy_sort_order():
    """Issue #3: under `--zdr` the tracker hands the chart a list sorted by ZDR
    *policy* price (unroutable models pushed to math.inf and therefore last),
    not by effective `price_1m`. The chart must still scale off the true maximum
    effective price and render a monotonic triangle.

    ZDR-policy rank order below (what tracker._rank_price_1m produces):
      gemini   policy 0.09  -> rank 0.09
      luna     policy 0.25  -> rank 0.25
      claude   policy 1.60  -> rank 1.60
      qwen     unroutable   -> rank math.inf (last), yet CHEAPEST effective
    """
    zdr_ordered = [
        ModelPrice(
            model="google/gemini-3.7-flash", price_1m=0.60, ma_7d=0.60, ma_3d=0.60,
            change_vs_7d_pct=0.0,
            price=PricePoint(0.6, 0.6, 0.60, policy_price_1m=0.09, is_policy_routable=True),
        ),
        ModelPrice(
            model="openai/gpt-5.6-luna", price_1m=1.20, ma_7d=1.20, ma_3d=1.20,
            change_vs_7d_pct=0.0,
            price=PricePoint(1.2, 1.2, 1.20, policy_price_1m=0.25, is_policy_routable=True),
        ),
        ModelPrice(
            model="anthropic/claude-myth-9", price_1m=2.40, ma_7d=2.40, ma_3d=2.40,
            change_vs_7d_pct=0.0,
            price=PricePoint(2.4, 2.4, 2.40, policy_price_1m=1.60, is_policy_routable=True),
        ),
        ModelPrice(
            model="qwen/qwen3.7-flash", price_1m=0.30, ma_7d=0.30, ma_3d=0.30,
            change_vs_7d_pct=0.0,
            price=PricePoint(0.3, 0.3, 0.30, policy_price_1m=None, is_policy_routable=False),
        ),
    ]
    # Guard: the input really is in ZDR-policy order, not effective-price order.
    ranks = [math.inf if p.price.policy_price_1m is None else p.price.policy_price_1m
             for p in zdr_ordered]
    assert ranks == sorted(ranks)
    assert zdr_ordered[0].price_1m != min(p.price_1m for p in zdr_ordered)

    lines = render_ascii_price_bar(zdr_ordered, max_bar_width=32)
    widths = _bar_widths(lines)

    # 4 models rendered, bars monotonically non-decreasing (the triangle shape).
    assert len(widths) == 4
    assert widths == sorted(widths)

    # Scale is the true maximum effective price (2.40), so nothing overflows and
    # the most expensive model is exactly max_bar_width wide.
    assert max(widths) == 32
    assert widths == [4, 8, 16, 32]  # 0.30/0.60/1.20/2.40 against a 2.40 scale

    # 🏆 [BEST] badges the true cheapest *effective* model, not the first input row.
    best_line = next(l for l in lines if "🏆 [BEST]" in l)
    assert "qwen/qwen3.7-flash" in best_line
    assert sum("🏆 [BEST]" in l for l in lines) == 1
