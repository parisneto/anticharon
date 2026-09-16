"""Golden pricing cases from ADR-2026-0002-TOKENS-CACHED (docs/plans/pricing-engine-v2/).

Five deterministic, independently-derived reference cases proving the
cache-aware 3-component blend (`anticharon.pricing.calculate_effective_cost`)
computes real effective cost correctly, and that the pre-ADR 2-component
formula (`calculate_legacy_cost`) overestimates it by the documented margin.
Pure logic layer of the ADR's trust hierarchy: no I/O, no mocks.
"""

import pytest

from anticharon.pricing import (
    calculate_effective_cost,
    calculate_legacy_cost,
    price_per_1m,
)

GOLDEN_CASES = [
    pytest.param(
        "flagship_coding_agent_gpt_5_6_sol",
        2.00, 10.00, 0.20,
        30_000, 170_000, 1_000,
        0.1040, 0.5174, 2.0398,
        id="case1_flagship_coding_agent",
    ),
    pytest.param(
        "zdr_enforced_azure_routing_gpt_5_6_sol",
        5.00, 30.00, 0.50,
        30_000, 170_000, 1_000,
        0.2650, 1.3184, 5.1244,
        id="case2_zdr_azure_routing",
    ),
    pytest.param(
        "ultra_cheap_flash_deepseek_v4_flash",
        0.07, 0.28, 0.014,
        3_700, 181_300, 500,
        0.002937, 0.0158, 0.0706,
        id="case3_ultra_cheap_flash",
    ),
    pytest.param(
        "cold_start_turn_zero_cache_gpt_5_6_sol",
        2.00, 10.00, 0.20,
        50_000, 0, 2_000,
        0.1200, 2.3077, 2.3077,
        id="case4_cold_start_zero_cache",
    ),
    pytest.param(
        "reasoning_model_stream_gpt_5_6_luna_pro",
        0.20, 1.20, 0.02,
        30_000, 120_000, 3_000,
        0.0120, 0.0784, 0.2196,
        id="case5_reasoning_model_stream",
    ),
]


@pytest.mark.parametrize(
    "model,prompt_price,completion_price,cache_read_price,"
    "uncached_tokens,cached_tokens,completion_tokens,"
    "expected_total_cost,expected_price_per_1m,expected_legacy_price_per_1m",
    GOLDEN_CASES,
)
def test_golden_case_effective_cost(
    model,
    prompt_price,
    completion_price,
    cache_read_price,
    uncached_tokens,
    cached_tokens,
    completion_tokens,
    expected_total_cost,
    expected_price_per_1m,
    expected_legacy_price_per_1m,
):
    total_cost = calculate_effective_cost(
        uncached_prompt_price_1m=prompt_price,
        cache_read_price_1m=cache_read_price,
        completion_price_1m=completion_price,
        uncached_tokens=uncached_tokens,
        cached_tokens=cached_tokens,
        completion_tokens=completion_tokens,
    )
    assert total_cost == pytest.approx(expected_total_cost, abs=1e-4), (
        f"{model}: total cost mismatch"
    )

    total_tokens = uncached_tokens + cached_tokens + completion_tokens
    effective_per_1m = price_per_1m(total_cost, total_tokens)
    assert effective_per_1m == pytest.approx(expected_price_per_1m, abs=1e-3), (
        f"{model}: $/1M mismatch"
    )


@pytest.mark.parametrize(
    "model,prompt_price,completion_price,cache_read_price,"
    "uncached_tokens,cached_tokens,completion_tokens,"
    "expected_total_cost,expected_price_per_1m,expected_legacy_price_per_1m",
    GOLDEN_CASES,
)
def test_golden_case_legacy_regression(
    model,
    prompt_price,
    completion_price,
    cache_read_price,
    uncached_tokens,
    cached_tokens,
    completion_tokens,
    expected_total_cost,
    expected_price_per_1m,
    expected_legacy_price_per_1m,
):
    """Regression guard: proves the ADR fix is load-bearing.

    Recomputes the pre-ADR 2-component price (all prompt tokens at listed
    rate, cache ignored) and asserts it matches the ADR's documented "Legacy
    Error" figure and — except for the 0%-cache case — diverges materially
    from the cache-aware effective price. If cached-token pricing regresses
    to the legacy formula, this test fails.
    """
    prompt_tokens = uncached_tokens + cached_tokens
    total_tokens = prompt_tokens + completion_tokens

    legacy_cost = calculate_legacy_cost(
        prompt_price_1m=prompt_price,
        completion_price_1m=completion_price,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    legacy_per_1m = price_per_1m(legacy_cost, total_tokens)
    assert legacy_per_1m == pytest.approx(expected_legacy_price_per_1m, abs=1e-3), (
        f"{model}: legacy $/1M mismatch"
    )

    effective_cost = calculate_effective_cost(
        uncached_prompt_price_1m=prompt_price,
        cache_read_price_1m=cache_read_price,
        completion_price_1m=completion_price,
        uncached_tokens=uncached_tokens,
        cached_tokens=cached_tokens,
        completion_tokens=completion_tokens,
    )
    effective_per_1m = price_per_1m(effective_cost, total_tokens)

    if cached_tokens == 0:
        # Case #4: 0% cache hit rate — legacy and cache-aware formulas must
        # agree exactly, since there's no cached bucket to mis-price.
        assert effective_per_1m == pytest.approx(legacy_per_1m, abs=1e-4)
    else:
        # Cache-heavy cases: legacy must overestimate real cost materially.
        # This is the assertion that fails if cached-token pricing is removed.
        assert legacy_per_1m > effective_per_1m * 1.5, (
            f"{model}: expected legacy formula to materially overestimate "
            f"cache-aware effective price (legacy={legacy_per_1m}, "
            f"effective={effective_per_1m})"
        )
