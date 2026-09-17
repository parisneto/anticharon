"""Cache-aware 3-component blended pricing formula (ADR-2026-0002-TOKENS-CACHED).

Pure calculation logic only — no network, no storage. This is the canonical
formula `docs/plans/pricing-engine-v2/PLAN.md` ("Core pricing semantics")
requires every downstream pricing path to use: `Price = (P_uncached ×
w_uncached) + (P_cache_read × w_cached) + (P_out × w_completion)`. A 2-component
`calculate_legacy_cost` is kept alongside it only to make the cached-token
regression measurable (see `tests/test_golden_pricing.py`), not as a live path.
"""


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
    """False only for a negative sentinel price, true otherwise.

    OpenRouter meta-router models (e.g. `openrouter/auto-beta`) list
    `pricing.prompt`/`pricing.completion` as the raw string `"-1"` to mean
    "no fixed price" (it routes to whatever backing model at that model's
    own price). Naively multiplying by 1,000,000 like every real price
    turns that into a -1,000,000.0/1M sentinel, which then sorts as the
    globally cheapest model everywhere pricing is compared. Zero is not a
    sentinel here — it's how genuine free/promo-tier models are listed.
    """
    return price_1m >= 0


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
