"""Analytical Intelligence and Historical Model Pricing Profiles for Anticharon."""

import math
import re
from datetime import date, timedelta
from typing import Any

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


ANALYTICS_WINDOW_DAYS = 30


def valid_observations(observations: list[dict[str, Any]] | None, today: date) -> dict[date, float]:
    """Distinct valid observation dates -> price, from `effective_prices.json` entries.

    Valid: parseable ISO date inside the analytics window (today minus 30 days
    through today), finite non-negative price (a genuine zero price counts).
    Each calendar date counts once (the minimum wins, as in storage); gaps stay
    gaps -- nothing is interpolated or fabricated.
    """
    earliest = today - timedelta(days=ANALYTICS_WINDOW_DAYS)
    by_day: dict[date, float] = {}
    for obs in observations or []:
        try:
            obs_date = date.fromisoformat(obs["date"])
            price = float(obs["effective_price_1m"])
        except (KeyError, ValueError, TypeError):
            continue
        if not math.isfinite(price) or price < 0 or not earliest <= obs_date <= today:
            continue
        by_day[obs_date] = min(price, by_day.get(obs_date, price))
    return by_day


def calculate_model_analytics(
    model_id: str,
    current_price: float,
    observations: list[dict[str, Any]] | None,
    today: date,
    candidate_prices: dict[str, float] | None = None,
    current_default: str | None = None,
    min_tracking_days_for_profile: int = 14,
) -> ModelAnalytics:
    """Calculate variance, historical delta, and the pricing profile from the
    real dated observations in `effective_prices.json` (the only analytics input).

    Maturity: `NEWLY_TRACKED` when the number of distinct valid observed
    calendar days in the 30-day window is below `min_tracking_days_for_profile`.
    Backfilled days count immediately and `first_seen` plays no role.

    Dated observations are authoritative: today's stored observation, when
    present, is the current price for every calculation and `current_price` (a
    separate live/exported quote) is ignored; only when today has no
    observation is the quote used, and `current_price_source` says which.
    Comparison baselines (d1/d7/d15/d30) are the latest real observation on or
    before that many days ago; when none exists the baseline is unavailable
    (`None`) and no classification or wording that requires it is produced.
    """
    by_day = valid_observations(observations, today)
    observed_days = sorted(by_day)
    observation_count = len(observed_days)

    current_price_source = "observation" if today in by_day else "quote"
    if current_price_source == "observation":
        current_price = by_day[today]
    series = dict(by_day)
    series.setdefault(today, current_price)
    all_prices = list(series.values())
    mean_price = sum(all_prices) / len(all_prices)
    var_price = sum((p - mean_price) ** 2 for p in all_prices) / len(all_prices)
    std_price = math.sqrt(var_price)
    cv_pct = (std_price / mean_price * 100) if mean_price > 0 else 0.0

    past = [(d, by_day[d]) for d in observed_days if d < today]

    def _ref(days_ago: int) -> float | None:
        cutoff = today - timedelta(days=days_ago)
        on_or_before = [p for d, p in past if d <= cutoff]
        return on_or_before[-1] if on_or_before else None

    d1, d7, d15, d30 = _ref(1), _ref(7), _ref(15), _ref(30)

    price_min_30d = min(all_prices)
    price_max_30d = max(all_prices)
    # A percentage needs a positive baseline: a zero baseline is flat only when the
    # price is still zero, and otherwise has no percentage (direction is still shown).
    delta_30d_pct: float | None
    if d30 is None or (d30 == 0 and current_price > 0):
        delta_30d_pct = None
    elif d30 == 0:
        delta_30d_pct = 0.0
    else:
        delta_30d_pct = (current_price - d30) / d30 * 100

    # Sparkline trajectory formatting
    if delta_30d_pct is None:
        arrow = "↑" if d30 == 0 else "───"  # zero baseline, positive price
    elif delta_30d_pct > 15.0:
        arrow = "↑"
    elif delta_30d_pct < -15.0:
        arrow = "↓"
    elif delta_30d_pct > 3.0:
        arrow = "↗"
    elif delta_30d_pct < -3.0:
        arrow = "↘"
    else:
        arrow = "───"

    sparkline = f"{f'${d30:.2f}' if d30 is not None else 'n/a'} ──{arrow} ${current_price:.2f}"

    history_vector: dict[str, float | None] = {"now": current_price}
    for days_ago in (1, 2, 3, 4, 5, 6, 7, 15, 30):
        history_vector[f"d{days_ago}"] = by_day.get(today - timedelta(days=days_ago))

    siblings = find_sibling_alternatives(model_id, current_price, candidate_prices or {})
    best_sibling = siblings[0] if siblings else None

    # Classification logic
    is_newly_tracked = observation_count < min_tracking_days_for_profile
    available_baselines = [p for p in (d7, d15, d30) if p is not None]
    prior_baseline = min(available_baselines) if available_baselines else None
    comparison = "<" if is_newly_tracked else "≥"
    classification_reason = (
        f"{observation_count} distinct observed days {comparison} "
        f"{min_tracking_days_for_profile} required for classification."
    )

    if is_newly_tracked:
        profile = "NEWLY_TRACKED"
        badge = "🌱 NEWLY_TRACKED"
        secondary_badge = None
        trend_direction = "cold_start"
        recommendation = (
            f"Insufficient price history yet ({observation_count} observed days, "
            f"{min_tracking_days_for_profile} required for classification)."
        )

    elif (prior_baseline is not None and prior_baseline > 0 and d1 is not None
          and (current_price - prior_baseline) / prior_baseline >= 0.25 and abs(d1 - current_price) < 1e-4):
        promo_pct = (current_price - prior_baseline) / prior_baseline * 100
        profile = "PROMO_ENDED"
        badge = "📈 PROMO_ENDED"
        trend_direction = "rising"
        if best_sibling:
            secondary_badge = "⚠️ SUNSETTING"
            recommendation = (
                f"Introductory promo ended (+{promo_pct:.1f}%). Sibling {best_sibling.model} "
                f"active at same/lower price (${best_sibling.price_1m:.3f}). Migrate to {best_sibling.model}."
            )
        else:
            secondary_badge = None
            recommendation = f"Introductory promo ended (+{promo_pct:.1f}%). Prior baseline was ${prior_baseline:.3f}."

    elif best_sibling and d30 is not None and current_price >= d30:
        profile = "SUNSETTING"
        badge = "⚠️ SUNSETTING"
        secondary_badge = None
        trend_direction = "rising" if current_price > d30 else "flat"  # d30 is available here
        recommendation = f"Vendor pushing migration to {best_sibling.model} (same or lower cost)."

    elif (delta_30d_pct is not None and delta_30d_pct <= -20.0 and prior_baseline is not None
          and current_price <= prior_baseline * 0.85):
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

    elif (None not in (d7, d15, d30) and delta_30d_pct is not None and 5.0 <= delta_30d_pct < 25.0
          and current_price >= d7 >= d15 >= d30):
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
        history_vector=history_vector,
        observation_count=observation_count,
        earliest_observation=observed_days[0].isoformat() if observed_days else None,
        latest_observation=observed_days[-1].isoformat() if observed_days else None,
        coverage_days=(observed_days[-1] - observed_days[0]).days + 1 if observed_days else 0,
        classification_reason=classification_reason,
        current_price_used=current_price,
        current_price_source=current_price_source,
    )
