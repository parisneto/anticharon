"""Tests for anticharon.log_parser: tokens_cached support (ADR-2026-0002-TOKENS-CACHED).

Layers per AGENTS.md Rule 8 / EXECUTION_CONTRACT.md §2:
- fixture-based parsing test with exact independently-derived expected math
- regression test against the real sanitized activity logs in docs/sample/
- failure/edge-path tests: missing file, missing tokens_cached column, malformed values
"""

from pathlib import Path

import pytest

from anticharon.log_parser import parse_activity_log

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_DIR = Path(__file__).parent.parent / "docs" / "sample"


def test_parse_activity_log_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        parse_activity_log(FIXTURES_DIR / "does_not_exist.csv")


def test_parse_activity_log_cache_split_exact_math():
    """4-row fixture with known cached/uncached/completion totals, including a
    blank tokens_cached cell and a malformed (non-numeric) one — both must
    fall back to 0 rather than crash the parse."""
    result = parse_activity_log(FIXTURES_DIR / "activity_log_cached.csv")

    assert result.records_count == 4
    assert result.total_prompt_tokens == 3800
    assert result.total_completion_tokens == 180
    assert result.total_cached_tokens == 1300
    assert result.total_uncached_tokens == 2500
    assert result.total_tokens == 3980

    assert result.weight_uncached_prompt == pytest.approx(0.628141, abs=1e-5)
    assert result.weight_cached_prompt == pytest.approx(0.326633, abs=1e-5)
    assert result.weight_completion == pytest.approx(0.045226, abs=1e-5)
    assert result.cache_hit_rate == pytest.approx(0.342105, abs=1e-5)

    # The 3-way split must fully partition total_tokens.
    assert (
        result.weight_uncached_prompt + result.weight_cached_prompt + result.weight_completion
        == pytest.approx(1.0, abs=1e-9)
    )

    assert result.weight_completion == pytest.approx(180 / 3980, abs=1e-6)


def test_parse_activity_log_no_cache_column_defaults_to_zero():
    """Older exports without a tokens_cached column must still parse — 100%
    uncached, matching pre-ADR behavior exactly."""
    result = parse_activity_log(FIXTURES_DIR / "activity_log_no_cache_column.csv")

    assert result.total_prompt_tokens == 3000
    assert result.total_cached_tokens == 0
    assert result.total_uncached_tokens == 3000
    assert result.cache_hit_rate == 0.0
    assert result.weight_cached_prompt == 0.0
    assert result.weight_uncached_prompt == pytest.approx(1.0 - result.weight_completion, abs=1e-9)


@pytest.mark.parametrize(
    "filename,expected_records,expected_prompt,expected_cached,expected_completion",
    [
        ("openrouter_activity_2026-08-24.csv", 159, 17_386_716, 14_216_867, 51_209),
        ("openrouter_activity_2026-09-15.csv", 570, 74_586_658, 56_299_237, 304_115),
    ],
)
def test_parse_real_sample_logs_cache_totals(
    filename, expected_records, expected_prompt, expected_cached, expected_completion
):
    """Regression guard against docs/sample/ real exports (ADR §'Empirical Data').

    Fails if tokens_cached parsing regresses to always-0 — the exact bug this
    ADR fixes (log_parser.py silently ignoring tokens_cached)."""
    result = parse_activity_log(SAMPLE_DIR / filename)

    assert result.records_count == expected_records
    assert result.total_prompt_tokens == expected_prompt
    assert result.total_cached_tokens == expected_cached
    assert result.total_completion_tokens == expected_completion

    # Both real exports are cache-heavy (75-82% per the ADR) — this is the
    # assertion that fails if cached-token support is removed again.
    assert result.cache_hit_rate > 0.7
    assert result.total_uncached_tokens == expected_prompt - expected_cached
    assert result.weight_cached_prompt > result.weight_uncached_prompt
