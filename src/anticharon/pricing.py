"""Cache-aware 3-component blended pricing formula (ADR-2026-0002-TOKENS-CACHED).

Pure calculation logic only — no network, no storage. This is the canonical
formula `docs/plans/pricing-engine-v2/PLAN.md` ("Core pricing semantics")
requires every downstream pricing path to use: `Price = (P_uncached ×
w_uncached) + (P_cache_read × w_cached) + (P_out × w_completion)`. A 2-component
`calculate_legacy_cost` is kept alongside it only to make the cached-token
regression measurable (see `tests/test_golden_pricing.py`), not as a live path.
"""


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
