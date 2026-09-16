#!/usr/bin/env python3
"""Dev utility: draw a random, diverse handful of OpenRouter model slugs for test fixtures.

Not part of the anticharon package or CLI. Pulls from several public, unauthenticated
`sort=` views on GET /api/v1/models (no API key needed) to get variety across cold-start
(newest), typical (most-popular), and price-extreme (cheapest/priciest) models, plus one
pure-random pick from the full catalog. Prints JSON to stdout; the receiver decides what
to do with it (skip duplicates of already-known test slugs, add new ones, etc.).

Usage:
    uv run python scripts/pick_random_test_models.py
    uv run python scripts/pick_random_test_models.py --count 5 --seed 42
"""

import argparse
import json
import random
import sys
from typing import Any, Dict, List

import requests

MODELS_URL = "https://openrouter.ai/api/v1/models"
TIMEOUT = 10.0

# Each source draws one candidate from a different slice of the catalog, for diversity.
SOURCES = [
    ("newest", "newest"),
    ("most_popular", "top-weekly"),
    ("cheapest", "pricing-low-to-high"),
    ("priciest", "pricing-high-to-low"),
    ("longest_context", "context-high-to-low"),
]


def fetch_sorted(sort: str) -> List[Dict[str, Any]]:
    """Fetch the catalog under a given sort order. Returns [] on any failure."""
    try:
        resp = requests.get(MODELS_URL, params={"sort": sort}, timeout=TIMEOUT)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except Exception as exc:
        print(f"[WARN] sort={sort} failed: {exc}", file=sys.stderr)
        return []


def summarize(model: Dict[str, Any], source: str) -> Dict[str, Any]:
    pricing = model.get("pricing", {}) or {}
    return {
        "slug": model.get("id"),
        "name": model.get("name"),
        "source": source,
        "context_length": model.get("context_length"),
        "prompt_price_1m": round(float(pricing.get("prompt", 0) or 0) * 1_000_000, 4),
        "completion_price_1m": round(float(pricing.get("completion", 0) or 0) * 1_000_000, 4),
    }


def draw(count: int, rng: random.Random) -> List[Dict[str, Any]]:
    picks: Dict[str, Dict[str, Any]] = {}

    for source_name, sort_param in SOURCES:
        if len(picks) >= count:
            break
        candidates = fetch_sorted(sort_param)
        candidates = [m for m in candidates if m.get("id") and m["id"] not in picks]
        if candidates:
            # Draw from the top slice of this sort, not always #1 -- more variety run to run.
            top_slice = candidates[: min(10, len(candidates))]
            chosen = rng.choice(top_slice)
            picks[chosen["id"]] = summarize(chosen, source_name)

    # Fill any remaining slots with pure-random picks from the unsorted catalog.
    if len(picks) < count:
        full_catalog = fetch_sorted("newest")  # any sort works; only used as a full listing here
        remaining = [m for m in full_catalog if m.get("id") and m["id"] not in picks]
        rng.shuffle(remaining)
        for model in remaining:
            if len(picks) >= count:
                break
            picks[model["id"]] = summarize(model, "random")

    return list(picks.values())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5, help="Number of models to draw (default: 5)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible draws")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    results = draw(args.count, rng)

    if not results:
        print(json.dumps({"status": "error", "message": "No models could be fetched.", "models": []}, indent=2))
        return 1

    print(json.dumps({"status": "success", "count": len(results), "models": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
