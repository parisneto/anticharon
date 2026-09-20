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


# --- GH-3: defensive safety against non-finite `price_1m` (Infinity/-Infinity/
# NaN). These should already be rejected upstream by
# anticharon.pricing.is_valid_listed_price, but the chart itself must never
# crash or misrender if one still reaches it. ---


def test_ascii_chart_positive_infinity_does_not_crash():
    """The original GH-3 crash: `inf / inf` is NaN, and `int(round(nan))`
    raised ValueError, taking down the whole chart on one bad entry."""
    prices = [
        ModelPrice(model="cheap/model", price_1m=0.5, ma_7d=0.5, change_vs_7d_pct=0.0),
        ModelPrice(model="broken/inf-model", price_1m=float("inf"), ma_7d=0.0, change_vs_7d_pct=0.0),
        ModelPrice(model="mid/model", price_1m=2.0, ma_7d=2.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)
    widths = _bar_widths(lines)
    assert len(widths) == 3
    assert all(w <= 32 for w in widths)


def test_ascii_chart_positive_infinity_scales_off_max_finite_price():
    prices = [
        ModelPrice(model="cheap/model", price_1m=0.5, ma_7d=0.5, change_vs_7d_pct=0.0),
        ModelPrice(model="broken/inf-model", price_1m=float("inf"), ma_7d=0.0, change_vs_7d_pct=0.0),
        ModelPrice(model="mid/model", price_1m=2.0, ma_7d=2.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)

    def _width_for(model):
        line = next(l for l in lines if model in l)
        m = re.search(r"(█+)", line)
        return len(m.group(1))

    # 0.5/2.0 * 32 = 8; 2.0/2.0 * 32 = 32 -- the infinite entry is excluded
    # from the scale computation and rendered capped at max_bar_width.
    assert _width_for("cheap/model") == 8
    assert _width_for("mid/model") == 32
    assert _width_for("broken/inf-model") <= 32

    # BEST follows the minimum *finite* effective price, not the sorted
    # position (an inf never sorts first, but this stays true regardless).
    best_line = next(l for l in lines if "🏆 [BEST]" in l)
    assert "cheap/model" in best_line
    assert sum("🏆 [BEST]" in l for l in lines) == 1


def test_ascii_chart_negative_infinity_does_not_crash_or_win_best():
    """A -inf sorts first (cheapest by naive comparison), but it must never
    be treated as the real cheapest effective price."""
    prices = [
        ModelPrice(model="broken/neg-inf-model", price_1m=float("-inf"), ma_7d=0.0, change_vs_7d_pct=0.0),
        ModelPrice(model="cheap/model", price_1m=0.5, ma_7d=0.5, change_vs_7d_pct=0.0),
        ModelPrice(model="mid/model", price_1m=2.0, ma_7d=2.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)
    widths = _bar_widths(lines)
    assert len(widths) == 3
    assert all(w <= 32 for w in widths)

    best_line = next(l for l in lines if "🏆 [BEST]" in l)
    assert "cheap/model" in best_line
    assert sum("🏆 [BEST]" in l for l in lines) == 1


def test_ascii_chart_nan_price_does_not_crash():
    """NaN comparisons never raise, but `int(round(nan))` does -- and NaN's
    sort position is undefined, so this only asserts non-crash + all other
    rows staying correct, not NaN's own row content."""
    prices = [
        ModelPrice(model="broken/nan-model", price_1m=float("nan"), ma_7d=0.0, change_vs_7d_pct=0.0),
        ModelPrice(model="cheap/model", price_1m=0.5, ma_7d=0.5, change_vs_7d_pct=0.0),
        ModelPrice(model="mid/model", price_1m=2.0, ma_7d=2.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)
    widths = _bar_widths(lines)
    assert len(widths) == 3
    assert all(w <= 32 for w in widths)

    def _width_for(model):
        line = next(l for l in lines if model in l)
        m = re.search(r"(█+)", line)
        return len(m.group(1))

    assert _width_for("cheap/model") == 8
    assert _width_for("mid/model") == 32
    # NaN never wins BEST (it can't equal `min()` of the finite set).
    best_line = next(l for l in lines if "🏆 [BEST]" in l)
    assert "cheap/model" in best_line
    assert sum("🏆 [BEST]" in l for l in lines) == 1


# --- GH-3: unsorted finite input, ties, and zero ---


def test_ascii_chart_unsorted_finite_input_still_monotonic():
    prices = [
        ModelPrice(model="mid/model", price_1m=2.0, ma_7d=2.0, change_vs_7d_pct=0.0),
        ModelPrice(model="cheap/model", price_1m=0.5, ma_7d=0.5, change_vs_7d_pct=0.0),
        ModelPrice(model="expensive/model", price_1m=4.0, ma_7d=4.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)
    widths = _bar_widths(lines)
    assert widths == sorted(widths)
    assert max(widths) == 32


def test_ascii_chart_tied_prices_single_best_badge():
    prices = [
        ModelPrice(model="tied/a", price_1m=1.0, ma_7d=1.0, change_vs_7d_pct=0.0),
        ModelPrice(model="tied/b", price_1m=1.0, ma_7d=1.0, change_vs_7d_pct=0.0),
        ModelPrice(model="expensive/model", price_1m=2.0, ma_7d=2.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)
    widths = _bar_widths(lines)
    assert len(widths) == 3
    assert widths == sorted(widths)
    # Exactly one BEST badge even with a tie at the minimum price.
    assert sum("🏆 [BEST]" in l for l in lines) == 1


def test_ascii_chart_zero_price_renders_minimum_bar_and_wins_best():
    prices = [
        ModelPrice(model="free/model", price_1m=0.0, ma_7d=0.0, change_vs_7d_pct=0.0),
        ModelPrice(model="paid/model", price_1m=3.0, ma_7d=3.0, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(prices, max_bar_width=32)
    widths = _bar_widths(lines)
    assert widths[0] == 1  # zero price -> minimal 1-block bar, no crash
    assert widths[1] == 32

    best_line = next(l for l in lines if "🏆 [BEST]" in l)
    assert "free/model" in best_line
