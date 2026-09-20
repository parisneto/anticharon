"""ASCII / TUI visualization engine for Anticharon price spectrum."""


from anticharon.models import ModelPrice


def render_ascii_price_bar(
    prices: list[ModelPrice],
    default_model: str | None = None,
    max_bar_width: int = 32
) -> list[str]:
    """Render a proportional ASCII bar chart illustrating relative model price distribution.
    
    The chart is always a spectrum of the effective `price_1m`, so it neither
    trusts nor requires the caller's ordering: callers may legitimately hand it
    a list sorted by something else (under `--zdr` the tracker ranks by *policy*
    price, pushing an unroutable model last even when its effective price is the
    cheapest). It therefore sorts a local working copy by `price_1m` and scales
    off the true maximum, rather than off whatever landed last (Issue #3).

    Args:
        prices: List of ModelPrice instances, in any order.
        default_model: The configured default model ID to badge with ★.
        max_bar_width: Maximum width of the block bar.

    Returns:
        List of formatted lines representing the chart.
    """
    if not prices:
        return []

    lines: list[str] = []
    lines.append("📊 RELATIVE PRICE SPECTRUM ($/1M Tokens):")
    lines.append("  ▲ Cheaper")

    ordered = sorted(prices, key=lambda p: p.price_1m)
    max_p = max(p.price_1m for p in ordered)

    # Avoid zero division when all prices are identical
    price_range = max_p if max_p > 0 else 1.0

    # Determine maximum length for model names to keep columns cleanly aligned
    max_name_len = max(len(p.model) for p in ordered)
    name_col_width = min(max(max_name_len, 24), 36)

    for idx, p in enumerate(ordered):
        # Truncate model name if excessively long
        name = p.model
        if len(name) > name_col_width:
            name = name[:name_col_width - 3] + "..."

        # Calculate proportional bar width (minimum 2 blocks, maximum max_bar_width)
        ratio = p.price_1m / price_range if price_range > 0 else 0.0
        bar_len = max(int(round(ratio * max_bar_width)), 2) if p.price_1m > 0 else 1
        bar = "█" * bar_len

        # Badges
        badges = []
        if idx == 0:
            badges.append("🏆 [BEST]")
        if default_model and p.model == default_model:
            badges.append("★ [DEFAULT]")

        badge_str = f" {' '.join(badges)}" if badges else ""
        lines.append(f"    {name:<{name_col_width}}  ${p.price_1m:<8.5f}  {bar}{badge_str}")

    lines.append("  ▼ More Expensive")
    return lines

if __name__ == "__main__":
    # Example usage for testing

    mock_prices = [
        ModelPrice(
            model="openai/gptx-neo-7",
            price_1m=2.25,
            ma_7d=7.90,
            change_vs_7d_pct=10.76,
        ),
        ModelPrice(
            model="anthropic/claude-Myth-9",
            price_1m=5.20,
            ma_7d=5.85,
            change_vs_7d_pct=-11.11,
        ),
        ModelPrice(
            model="meta/titan-7",
            price_1m=2.15,
            ma_7d=1.95,
            change_vs_7d_pct=10.26,
        ),
        ModelPrice(
            model="xai/grok-heavy-8d",
            price_1m=3.70,
            ma_7d=4.10,
            change_vs_7d_pct=-9.76,
        ),
        ModelPrice(
            model="google/gemini-ultron-4.7",
            price_1m=1.25,
            ma_7d=1.25,
            change_vs_7d_pct=0.00,
        ),
        ModelPrice(
            model="deepseek/deepseek-z32",
            price_1m=0.98,
            ma_7d=0.55,
            change_vs_7d_pct=-30.91,
        ),
    ]

    mock_prices.sort(key=lambda x: x.price_1m)
    chart_lines = render_ascii_price_bar(mock_prices, default_model="openai/gptx-neo-7", max_bar_width=32)
    
    print("-" * 74)
    print()
    print("\n".join(chart_lines))
    print("-" * 74)