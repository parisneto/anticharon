"""Cache-aware 3-component blended pricing formula (ADR-2026-0002-TOKENS-CACHED).

Pure calculation logic only — no network, no storage. This is the canonical
formula `docs/plans/pricing-engine-v2/PLAN.md` ("Core pricing semantics")
requires every downstream pricing path to use: `Price = (P_uncached ×
w_uncached) + (P_cache_read × w_cached) + (P_out × w_completion)`. A 2-component
`calculate_legacy_cost` is kept alongside it only to make the cached-token
regression measurable (see `tests/test_golden_pricing.py`), not as a live path.
"""

import math


def parse_required_price_1m(pricing: dict, field: str) -> float | None:
    """Parse a *required* raw per-token price field (`"prompt"`/`"completion"`)
    from an OpenRouter `pricing` dict into $/1M, or `None` if the field is
    missing/blank/malformed (PE2-001-adjacent defect PE2-002 -- do not confuse
    "absent" with "genuine numeric zero").

    Live-verified 2026-09-17: every real bulk-catalog model and every real
    per-endpoint entry always includes both `prompt` and `completion` as
    present string keys, including real free (`:free`) models, which list
    them explicitly as `"0"`, never by omission. So a *missing* key, `None`
    value, blank string, or non-numeric value is never a legitimate free
    price -- it is missing/partial pricing data, and must not silently
    become `0.0` (a fabricated free endpoint). Only a present, parseable
    numeric value -- including a real `0` -- is a valid price.
    """
    if field not in pricing:
        return None
    raw = pricing.get(field)
    if raw is None:
        return None
    if isinstance(raw, str) and raw.strip() == "":
        return None
    try:
        return float(raw) * 1_000_000
    except (ValueError, TypeError):
        return None


def is_valid_listed_price(price_1m: float) -> bool:
    """False for a negative sentinel price or a non-finite value, true otherwise.

    OpenRouter meta-router models (e.g. `openrouter/auto-beta`) list
    `pricing.prompt`/`pricing.completion` as the raw string `"-1"` to mean
    "no fixed price" (it routes to whatever backing model at that model's
    own price). Naively multiplying by 1,000,000 like every real price
    turns that into a -1,000,000.0/1M sentinel, which then sorts as the
    globally cheapest model everywhere pricing is compared. Zero is not a
    sentinel here — it's how genuine free/promo-tier models are listed.

    `Infinity`/`-Infinity`/`NaN` are also rejected here (GH-3): `float()`
    happily parses those strings, so `parse_required_price_1m` can return a
    non-finite value for a malformed upstream catalog entry. This is the
    single boundary every tracker/discovery call site already gates on, so
    rejecting non-finite values here keeps them out of chart rendering and
    all other downstream pricing math without touching each call site.
    """
    return math.isfinite(price_1m) and price_1m >= 0


def calculate_effective_cost(
    uncached_prompt_price_1m: float,
    cache_read_price_1m: float,
    completion_price_1m: float,
    uncached_tokens: int,
    cached_tokens: int,
    completion_tokens: int,
) -> float:
    """Total dollar cost for a token usage split, cache-aware 3-component blend.

    cost = (uncached_tokens/1e6) * P_uncached
         + (cached_tokens/1e6)   * P_cache_read
         + (completion_tokens/1e6) * P_completion
    """
    return (
        (uncached_tokens / 1_000_000) * uncached_prompt_price_1m
        + (cached_tokens / 1_000_000) * cache_read_price_1m
        + (completion_tokens / 1_000_000) * completion_price_1m
    )


def price_per_1m(total_cost: float, total_tokens: int) -> float:
    """Blended $/1M rate implied by a total cost over a token usage split."""
    if total_tokens <= 0:
        return 0.0
    return total_cost / total_tokens * 1_000_000


def blended_rate_1m(
    uncached_prompt_price_1m: float,
    cache_read_price_1m: float,
    completion_price_1m: float,
    weight_uncached: float,
    weight_cached: float,
    weight_completion: float,
) -> float:
    """Blended $/1M rate directly from calibrated weights (no token counts needed).

    Equivalent to `calculate_effective_cost` over a usage split whose
    uncached/cached/completion token counts are in the same proportion as the
    weights -- the form tracker.py/discovery.py use, since they only have a
    calibrated *mix* (default or from `anticharon calibrate`), not per-request
    token counts.
    """
    return (
        uncached_prompt_price_1m * weight_uncached
        + cache_read_price_1m * weight_cached
        + completion_price_1m * weight_completion
    )


def derive_cache_hit_rate(weight_uncached_prompt: float, weight_cached_prompt: float) -> float:
    """The real prompt cache-hit rate (cached prompt tokens / total prompt
    tokens) derived from the calibrated 3-way weights, for display purposes
    only (PE2-008).

    `weight_cached_prompt` and `weight_uncached_prompt` are each a share of
    *all* tokens (`Total_Cached / Total_Tokens`, `Total_Uncached / Total_Tokens`
    per ADR-2026-0002-TOKENS-CACHED §1 "Activity Log Calibration"), where
    `Total_Tokens` includes completion tokens -- neither is itself the
    cache-hit rate, which is specifically `Total_Cached / Total_Prompt`
    (cached tokens as a share of *prompt* tokens only, excluding completion).
    Algebraically: `weight_cached_prompt / (weight_uncached_prompt +
    weight_cached_prompt) = (Cached/Total) / (Prompt/Total) = Cached/Prompt`,
    which is exactly the cache-hit rate -- this is the correct derivation, not
    a fresh assumption.

    Zero-prompt-weight behavior (both weights are `0`, i.e. a 100%-completion
    mix -- degenerate but not impossible if a user manually miscalibrates):
    explicitly defined here as `0.0` ("no prompt tokens were ever cached,
    because there were effectively no prompt tokens"), never a division by
    zero and never a fabricated nonzero rate.
    """
    total_prompt_weight = weight_uncached_prompt + weight_cached_prompt
    if total_prompt_weight <= 0:
        return 0.0
    return weight_cached_prompt / total_prompt_weight


def resolve_cache_read_price_1m(prompt_price_1m: float, cache_read_price_1m: float | None) -> float:
    """OpenRouter omits `pricing.input_cache_read` for some endpoints. Per the
    original ADR's fallback rule, default it to 10% of the uncached prompt
    price rather than treating missing cache pricing as free (0)."""
    if cache_read_price_1m is None:
        return prompt_price_1m * 0.10
    return cache_read_price_1m


def calculate_legacy_cost(
    prompt_price_1m: float,
    completion_price_1m: float,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Pre-ADR 2-component cost: prices every prompt token (cached + uncached)
    at the listed prompt rate, ignoring cache-read pricing entirely. This is
    the exact defect ADR-2026-0002-TOKENS-CACHED fixes — kept only so tests
    can prove the new formula corrects a real, quantifiable overestimate.
    """
    return (
        (prompt_tokens / 1_000_000) * prompt_price_1m
        + (completion_tokens / 1_000_000) * completion_price_1m
    )


# Service-tier tokens in an endpoint `tag` (e.g. `openai/flex`, `google-vertex/global/priority`).
# Quantization (`fp8`), region (`eu`, `global`) and `zdr` segments are NOT tiers (EH-8, D-9).
SERVICE_TIER_TOKENS = frozenset({"flex", "fast", "priority", "ultrafast", "turbo", "batch"})


def is_service_tier_tag(tag: str | None) -> bool:
    """True when any `/`-separated segment of an endpoint tag is a service-tier token."""
    return any(segment in SERVICE_TIER_TOKENS for segment in (tag or "").split("/"))


def map_endpoint_tags(series: list[dict], endpoints: list[dict]) -> dict[str, str]:
    """Endpoint UUID -> tag, joining the frontend listed-pricing series to the public
    endpoints API at each series' latest point.

    Join key: (tag prefix, input $/1M, output $/1M), then (prefix, input), then
    (prefix, output). The tag prefix equals the frontend `providerSlug`; the public
    `provider_name` does not ("Google" vs "google-vertex"). When several tags match
    and disagree on tier class, a service-tier tag wins (non-standard). Unmatched
    UUIDs are omitted."""
    full: dict[tuple, set[str]] = {}
    by_in: dict[tuple, set[str]] = {}
    by_out: dict[tuple, set[str]] = {}
    for ep in endpoints:
        tag = ep.get("tag") or ""
        prefix = tag.split("/")[0]
        pricing = ep.get("pricing") or {}
        try:
            p_in = round(float(pricing["prompt"]) * 1_000_000, 4)
            p_out = round(float(pricing["completion"]) * 1_000_000, 4)
        except (KeyError, TypeError, ValueError):
            continue
        full.setdefault((prefix, p_in, p_out), set()).add(tag)
        by_in.setdefault((prefix, p_in), set()).add(tag)
        by_out.setdefault((prefix, p_out), set()).add(tag)

    def latest(item: dict, key: str) -> float | None:
        points = item.get(key) or []
        try:
            return round(float(points[-1]["value"]), 4)
        except (IndexError, KeyError, TypeError, ValueError):
            return None

    result: dict[str, str] = {}
    for item in series:
        uuid, slug = item.get("endpointId"), item.get("providerSlug") or ""
        p_in, p_out = latest(item, "input"), latest(item, "output")
        if not uuid or p_in is None:
            continue
        candidates = (full.get((slug, p_in, p_out)) or by_in.get((slug, p_in))
                      or (by_out.get((slug, p_out)) if p_out is not None else None))
        if not candidates:
            continue
        tier_tags = [t for t in candidates if is_service_tier_tag(t)]
        result[uuid] = min(tier_tags or candidates)
    return result


def derive_listed_daily_prices(
    series: list[dict],
    excluded_endpoint_ids: frozenset[str],
    weights: tuple[float, float, float],
    today,
    now,
    window_days: int = 30,
) -> list[dict]:
    """Daily Anticharon-blended prices from OpenRouter *listed* step series (Phase A,
    side-by-side only).

    For each UTC day in the window the value is the cheapest non-excluded endpoint's
    `blended_rate_1m` of the listed input/output/cacheRead prices in effect at the end
    of that day (`now` for today). An endpoint with no point yet that day is skipped;
    a missing cacheRead falls back to 10% of input, as the live quote does."""
    from datetime import datetime, time, timedelta, timezone

    def parse(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def value_at(points: list[dict], moment: datetime) -> float | None:
        current = None
        for point in points or []:
            try:
                if parse(point["at"]) <= moment:
                    current = float(point["value"])
                else:
                    break
            except (KeyError, TypeError, ValueError):
                continue
        return current

    w_uncached, w_cached, w_completion = weights
    observations = []
    for offset in range(window_days, -1, -1):
        day = today - timedelta(days=offset)
        moment = now if offset == 0 else datetime.combine(day, time(23, 59, 59), tzinfo=timezone.utc)
        best = None
        for endpoint in series:
            if endpoint.get("endpointId") in excluded_endpoint_ids:
                continue
            p_in, p_out = value_at(endpoint.get("input"), moment), value_at(endpoint.get("output"), moment)
            if p_in is None or p_out is None:
                continue
            p_cache = resolve_cache_read_price_1m(p_in, value_at(endpoint.get("cacheRead"), moment))
            rate = blended_rate_1m(p_in, p_cache, p_out, w_uncached, w_cached, w_completion)
            if best is None or rate < best:
                best = rate
        if best is not None:
            observations.append({"date": day.isoformat(), "effective_price_1m": best})
    return observations
