"""Parser for OpenRouter activity log CSVs to calculate token mix ratios."""

import csv
from pathlib import Path

from anticharon.models import PromptMixResult


def _parse_token_count(raw: str | None) -> int:
    """Parse a CSV token-count cell, defaulting to 0 for blank/missing/malformed values."""
    try:
        return int(float(raw)) if raw else 0
    except (ValueError, TypeError):
        return 0


def parse_activity_log(csv_path: Path | str) -> PromptMixResult:
    """Ingest an OpenRouter activity log CSV and calculate token mix weights.

    Reads `tokens_cached` (ADR-2026-0002-TOKENS-CACHED) alongside `tokens_prompt`/
    `tokens_completion` and splits prompt tokens into uncached/cached buckets, so
    downstream cache-aware pricing (see `docs/plans/pricing-engine-v2/`) can use a
    real calibrated cache-hit-rate instead of treating all prompt tokens as
    uncached. Older logs without a `tokens_cached` column parse fine and default
    that bucket to 0 (100% uncached), matching pre-ADR behavior.
    """
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"OpenRouter activity log not found at: {path}")

    total_prompt = 0
    total_completion = 0
    total_cached = 0
    records_count = 0

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records_count += 1
            total_prompt += _parse_token_count(row.get("tokens_prompt", "0"))
            total_completion += _parse_token_count(row.get("tokens_completion", "0"))
            total_cached += _parse_token_count(row.get("tokens_cached", "0"))

    total_uncached = total_prompt - total_cached
    total_tokens = total_prompt + total_completion

    if total_tokens > 0:
        weight_completion = total_completion / total_tokens
        weight_uncached_prompt = total_uncached / total_tokens
        weight_cached_prompt = total_cached / total_tokens
    else:
        # Fallback to default if log is empty
        weight_completion = 0.0078
        weight_uncached_prompt = 0.9922
        weight_cached_prompt = 0.0

    cache_hit_rate = (total_cached / total_prompt) if total_prompt > 0 else 0.0

    return PromptMixResult(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_tokens,
        weight_completion=weight_completion,
        records_count=records_count,
        total_cached_tokens=total_cached,
        total_uncached_tokens=total_uncached,
        weight_uncached_prompt=weight_uncached_prompt,
        weight_cached_prompt=weight_cached_prompt,
        cache_hit_rate=cache_hit_rate
    )
