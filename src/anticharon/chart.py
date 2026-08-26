"""ASCII / TUI visualization engine for Anticharon price spectrum."""

from typing import List, Optional
from anticharon.models import ModelPrice


def render_ascii_price_bar(
    prices: List[ModelPrice],
    default_model: Optional[str] = None,
    max_bar_width: int = 32
) -> List[str]:
    """Render a proportional ASCII bar chart illustrating relative model price distribution.
    
    Args:
        prices: Sorted list of ModelPrice instances (cheapest to most expensive).
        default_model: The configured default model ID to badge with ★.
        max_bar_width: Maximum width of the block bar.
        
    Returns:
        List of formatted lines representing the chart.
    """
    if not prices:
        return []

    lines: List[str] = []
    lines.append("📊 RELATIVE PRICE SPECTRUM ($/1M Tokens):")
    lines.append("  ▲ Cheaper")

    min_p = prices[0].price_1m
    max_p = prices[-1].price_1m

    # Avoid zero division when all prices are identical
    price_range = max_p if max_p > 0 else 1.0

    # Determine maximum length for model names to keep columns cleanly aligned
    max_name_len = max(len(p.model) for p in prices)
    name_col_width = min(max(max_name_len, 24), 36)

    for idx, p in enumerate(prices):
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
