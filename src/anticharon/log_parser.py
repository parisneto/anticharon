"""Parser for OpenRouter activity log CSVs to calculate token mix ratios."""

import csv
from pathlib import Path
from anticharon.models import PromptMixResult


def parse_activity_log(csv_path: Path | str) -> PromptMixResult:
    """Ingest an OpenRouter activity log CSV and calculate prompt/completion token weights."""
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"OpenRouter activity log not found at: {path}")

    total_prompt = 0
    total_completion = 0
    records_count = 0

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records_count += 1
            # tokens_prompt
            raw_prompt = row.get("tokens_prompt", "0")
            try:
                prompt_val = int(float(raw_prompt)) if raw_prompt else 0
            except (ValueError, TypeError):
                prompt_val = 0

            # tokens_completion
            raw_completion = row.get("tokens_completion", "0")
            try:
                comp_val = int(float(raw_completion)) if raw_completion else 0
            except (ValueError, TypeError):
                comp_val = 0

            total_prompt += prompt_val
            total_completion += comp_val

    total_tokens = total_prompt + total_completion
    if total_tokens > 0:
        weight_prompt = total_prompt / total_tokens
        weight_completion = total_completion / total_tokens
    else:
        # Fallback to default if log is empty
        weight_prompt = 0.9922
        weight_completion = 0.0078

    return PromptMixResult(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_tokens=total_tokens,
        weight_prompt=weight_prompt,
        weight_completion=weight_completion,
        records_count=records_count
    )
