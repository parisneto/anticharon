"""Tests for anticharon.chart: ASCII price spectrum rendering (unchanged by
the pricing-engine-v2 rework -- ModelPrice.price_1m stays the sort/chart key)."""

from anticharon.chart import render_ascii_price_bar
from anticharon.models import ModelPrice


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
