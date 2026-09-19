"""Analytical Intelligence and Historical Model Pricing Profiles for Anticharon."""

import math
import re

from anticharon.models import ModelAnalytics, SiblingAlternative


def parse_model_family(model_id: str) -> tuple[str, str, float, str]:
    """Parse model identifier into (provider, prefix, version_num, suffix).
    
    Example:
      'google/gemini-3.7-flash' -> ('google', 'gemini-', 3.7, '-flash')
      'deepseek/deepseek-v4-pro-0813' -> ('deepseek', 'deepseek-v', 4.0, '-pro-0813')
    """
    if "/" in model_id:
        provider, slug = model_id.split("/", 1)
    else:
        provider, slug = "", model_id

    # Match prefix, numerical version, and suffix
    match = re.match(r"^([a-zA-Z\-_]+?)(\d+(?:\.\d+)?)(.*)$", slug)
    if match:
        prefix = match.group(1)
        try:
            ver = float(match.group(2))
        except ValueError:
            ver = 0.0
        suffix = match.group(3)
        return provider.lower(), prefix.lower(), ver, suffix.lower()

    return provider.lower(), slug.lower(), 0.0, ""


def find_sibling_alternatives(
    model_id: str,
    current_price: float,
    candidate_prices: dict[str, float]
) -> list[SiblingAlternative]:
    """Identify newer/superior version siblings in the same model family that are equal or cheaper."""
    provider, prefix, ver, suffix = parse_model_family(model_id)
    if ver <= 0.0:
        return []

    alternatives: list[SiblingAlternative] = []
    for other_id, other_price in candidate_prices.items():
        if other_id == model_id:
            continue

        o_provider, o_prefix, o_ver, o_suffix = parse_model_family(other_id)
        if o_provider == provider and o_prefix == prefix:
            # Check if other model is a higher version and same or cheaper in price
            if o_ver > ver and other_price <= (current_price * 1.05):
                diff_pct = ((other_price - current_price) / current_price * 100) if current_price > 0 else 0.0
                alternatives.append(SiblingAlternative(
                    model=other_id,
                    price_1m=other_price,
                    relation="newer_version",
                    price_diff_pct=diff_pct
                ))

    alternatives.sort(key=lambda x: (x.price_1m, -parse_model_family(x.model)[2]))
    return alternatives


def calculate_model_analytics(
    model_id: str,
    current_price: float,
    history_prices: list[float | None],
    candidate_prices: dict[str, float] | None = None,
    current_default: str | None = None,
    min_tracking_days_for_profile: int = 14,
    tracking_days_elapsed: int | None = None,
) -> ModelAnalytics:
    """Calculate statistical variance, historical delta, and assign pricing profile.

    `history_prices` is the 9-slot [d1..d7, d15, d30] array with nullable
    entries -- `None` means "no real observation for that day yet," never a
    fabricated duplicate of `current_price` (ADR-2026-0002-TOKENS-CACHED /
    PLAN.md "Storage architecture"). `tracking_days_elapsed` (elapsed calendar
    days since the model was first tracked) drives `NEWLY_TRACKED`, not a
    slot count -- those diverge once backfill can leave gaps (e.g. `d1` and
    `d15` populated but nothing between). `tracking_days_elapsed=None` (unknown)
    is treated the same as "not enough elapsed time" -- the safe default.
    """
    padded_hist: list[float | None] = list(history_prices)[:9]
    padded_hist.extend([None] * (9 - len(padded_hist)))

    real_hist = [p for p in padded_hist if p is not None]
    all_prices = [current_price] + real_hist
    mean_price = sum(all_prices) / len(all_prices)
    var_price = sum((p - mean_price) ** 2 for p in all_prices) / len(all_prices)
    std_price = math.sqrt(var_price)
    cv_pct = (std_price / mean_price * 100) if mean_price > 0 else 0.0

    def _ref(value: float | None) -> float:
        """Defensive reference point for classification heuristics only. Never
        exposed as a stored/fabricated observation -- `history_vector` below
        keeps the real `None`."""
        return value if value is not None else current_price

    d1 = _ref(padded_hist[0])
    d7 = _ref(padded_hist[6])
    d15 = _ref(padded_hist[7])
    d30 = _ref(padded_hist[8])

    price_min_30d = min(all_prices)
    price_max_30d = max(all_prices)
    delta_30d_pct = ((current_price - d30) / d30 * 100) if d30 > 0 else 0.0

    # Sparkline trajectory formatting
    if delta_30d_pct > 15.0:
        arrow = "↑"
    elif delta_30d_pct < -15.0:
        arrow = "↓"
    elif delta_30d_pct > 3.0:
        arrow = "↗"
    elif delta_30d_pct < -3.0:
        arrow = "↘"
    else:
        arrow = "───"

    sparkline = f"${d30:.2f} ──{arrow} ${current_price:.2f}"

    history_vector = {
        "now": current_price,
        "d1": padded_hist[0],
        "d2": padded_hist[1],
        "d3": padded_hist[2],
        "d4": padded_hist[3],
        "d5": padded_hist[4],
        "d6": padded_hist[5],
        "d7": padded_hist[6],
        "d15": padded_hist[7],
        "d30": padded_hist[8]
    }

    siblings = find_sibling_alternatives(model_id, current_price, candidate_prices or {})
    best_sibling = siblings[0] if siblings else None

    # Classification logic
    is_newly_tracked = tracking_days_elapsed is None or tracking_days_elapsed < min_tracking_days_for_profile
    prior_baseline = min(d30, d15, d7)

    if is_newly_tracked:
        profile = "NEWLY_TRACKED"
        badge = "🌱 NEWLY_TRACKED"
        secondary_badge = None
        trend_direction = "cold_start"
        elapsed_str = "unknown" if tracking_days_elapsed is None else f"{tracking_days_elapsed}d"
        recommendation = (
            f"Insufficient tracking history yet ({elapsed_str} elapsed, "
            f"{min_tracking_days_for_profile}d required for classification)."
        )

    elif ((current_price - prior_baseline) / prior_baseline >= 0.25) and abs(d1 - current_price) < 1e-4:
        profile = "PROMO_ENDED"
        badge = "📈 PROMO_ENDED"
        trend_direction = "rising"
        if best_sibling:
            secondary_badge = "⚠️ SUNSETTING"
            recommendation = (
                f"Introductory promo ended (+{delta_30d_pct:.1f}%). Sibling {best_sibling.model} "
                f"active at same/lower price (${best_sibling.price_1m:.3f}). Migrate to {best_sibling.model}."
            )
        else:
            secondary_badge = None
            recommendation = f"Introductory promo ended (+{delta_30d_pct:.1f}%). Prior baseline was ${prior_baseline:.3f}."

    elif best_sibling and current_price >= d30:
        profile = "SUNSETTING"
        badge = "⚠️ SUNSETTING"
        secondary_badge = None
        trend_direction = "rising" if delta_30d_pct > 0 else "flat"
        recommendation = f"Vendor pushing migration to {best_sibling.model} (same or lower cost)."

    elif delta_30d_pct <= -20.0 and current_price <= (min(d30, d15, d7) * 0.85):
        profile = "DISCOUNTED"
        badge = "🏷️ DISCOUNTED"
        secondary_badge = None
        trend_direction = "dropping"
        recommendation = f"Active price cut ({delta_30d_pct:.1f}% vs 30d). High-value task opportunity."

    elif cv_pct >= 12.0:
        profile = "VOLATILE"
        badge = "⚡ VOLATILE"
        secondary_badge = None
        trend_direction = "erratic"
        recommendation = f"High variance (CV: {cv_pct:.1f}%). Provider rates fluctuate unpredictably."

    elif 5.0 <= delta_30d_pct < 25.0 and (current_price >= d7 >= d15 >= d30):
        profile = "CREEPING_INFLATION"
        badge = "🐌 CREEPING"
        secondary_badge = None
        trend_direction = "rising"
        recommendation = f"Stealth inflation drift (+{delta_30d_pct:.1f}% over 30d). Monitor trend."

    elif cv_pct < 2.5:
        profile = "STABLE"
        badge = "🛡️ STABLE"
        secondary_badge = None
        trend_direction = "flat"
        if current_default and model_id == current_default:
            recommendation = "Active default model; highly stable mature pricing baseline."
        else:
            recommendation = "Mature, highly stable baseline pricing. Low budget risk."

    else:
        profile = "MODERATE"
        badge = "⚖️ MODERATE"
        secondary_badge = None
        trend_direction = "mild"
        recommendation = f"Normal price fluctuation (CV: {cv_pct:.1f}%)."

    return ModelAnalytics(
        profile=profile,
        badge=badge,
        secondary_badge=secondary_badge,
        trend_direction=trend_direction,
        volatility_cv_pct=cv_pct,
        price_min_30d=price_min_30d,
        price_max_30d=price_max_30d,
        change_vs_30d_pct=delta_30d_pct,
        trajectory_sparkline=sparkline,
        recommendation=recommendation,
        sibling_alternatives=siblings,
        history_vector=history_vector
    )
