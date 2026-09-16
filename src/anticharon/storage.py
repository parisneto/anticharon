"""Storage: compact history.csv (fast-read summary) + granular effective_prices.json
(per-model, per-provider daily observations -- the source of truth history.csv's
d1..d7/d15/d30 and moving averages are precalculated from, per
docs/plans/pricing-engine-v2/PLAN.md's "Storage architecture" section).
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from anticharon.models import PriceRecord

CSV_HEADER = (
    "model,last_updated,effective_price_1m,advertised_prompt_1m,advertised_completion_1m,"
    "ma_3d,ma_7d,d1,d2,d3,d4,d5,d6,d7,d15,d30"
)

# d1..d7, d15, d30: how many calendar days ago each slot represents.
HISTORY_SLOT_DAYS_AGO = [1, 2, 3, 4, 5, 6, 7, 15, 30]

DEFAULT_EFFECTIVE_PRICES_STALE_HOURS = 24.0


def _parse_nullable_float(raw: str) -> Optional[float]:
    """Empty string = no real observation yet, never a fabricated 0.0/duplicate."""
    raw = raw.strip()
    if raw == "":
        return None
    return float(raw)


def read_history(history_path: Path) -> Dict[str, PriceRecord]:
    """Read historical price records from CSV file."""
    history: Dict[str, PriceRecord] = {}
    if not history_path.exists():
        return history

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            lines = [line.rstrip("\n") for line in f if line.strip()]
            if len(lines) <= 1:
                return history

            for line in lines[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 16:
                    model = parts[0]
                    last_updated = parts[1]
                    effective_price_1m = float(parts[2])
                    advertised_prompt_1m = float(parts[3])
                    advertised_completion_1m = float(parts[4])
                    ma_3d = float(parts[5])
                    ma_7d = float(parts[6])
                    prices = [_parse_nullable_float(p) for p in parts[7:16]]  # d1..d7, d15, d30
                    history[model] = PriceRecord(
                        model=model,
                        last_updated=last_updated,
                        effective_price_1m=effective_price_1m,
                        advertised_prompt_1m=advertised_prompt_1m,
                        advertised_completion_1m=advertised_completion_1m,
                        ma_3d=ma_3d,
                        ma_7d=ma_7d,
                        prices=prices
                    )
    except Exception:
        pass
    return history


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{round(value, 6):.6f}".rstrip("0").rstrip(".")
    return str(value)


def write_history(records: List[List[Any]], history_path: Path) -> None:
    """Persist updated price records to CSV file. A `None` cell writes as empty
    (no observation yet) rather than a fabricated value."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, "w", encoding="utf-8") as f:
        f.write(CSV_HEADER + "\n")
        for rec in records:
            f.write(",".join(_format_cell(x) for x in rec) + "\n")


# ---------------------------------------------------------------------------
# Granular effective_prices.json store: per-model, per-provider daily
# observations. history.csv's d1..d30/MA columns are derived from this file,
# not the other way around.
# ---------------------------------------------------------------------------


def get_effective_prices_path(data_dir: Path) -> Path:
    return data_dir / "effective_prices.json"


def read_effective_prices(path: Path) -> Dict[str, Any]:
    """Read the granular store. Missing/corrupt file -> empty store (no crash),
    same graceful-degradation contract as every other local read in this codebase."""
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_effective_prices(store: Dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=2)


def is_model_backfill_stale(
    store: Dict[str, Any],
    model_id: str,
    max_age_hours: float = DEFAULT_EFFECTIVE_PRICES_STALE_HOURS,
    now: Optional[datetime] = None,
) -> bool:
    """A model with no entry yet, or one whose `last_synced` is missing/older than
    `max_age_hours`, is due for a fresh backfill fetch. Independent of history.csv's
    per-run cadence -- refreshed only when actually stale, not on every `anticharon run`."""
    entry = store.get(model_id)
    if not entry or not entry.get("last_synced"):
        return True
    try:
        last_synced = datetime.fromisoformat(entry["last_synced"])
    except (ValueError, TypeError):
        return True
    now = now or datetime.now(timezone.utc)
    if last_synced.tzinfo is None:
        last_synced = last_synced.replace(tzinfo=timezone.utc)
    age_hours = (now - last_synced).total_seconds() / 3600.0
    return age_hours >= max_age_hours


def derive_history_window(
    observations: List[Dict[str, Any]],
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Precalculate history.csv's d1..d7/d15/d30 + ma_3d/ma_7d from the granular
    per-day observations, instead of shifting a list once per run (see PLAN.md's
    "Same-day-rerun bug fix" -- this redesign makes that whole class of bug moot:
    re-deriving from dated observations is idempotent no matter how many times a
    day `anticharon run` executes).

    Each observation: {"date": "YYYY-MM-DD", "effective_price_1m": float}.
    One observation per calendar day is expected (already reduced to the
    cheapest-endpoint blended rate for that day); if a day has more than one,
    the minimum is used. Missing days stay `None` -- never fabricated.
    """
    today = today or datetime.now(timezone.utc).date()

    by_day: Dict[date, float] = {}
    for obs in observations:
        try:
            obs_date = date.fromisoformat(obs["date"])
            price = float(obs["effective_price_1m"])
        except (KeyError, ValueError, TypeError):
            continue
        if obs_date not in by_day or price < by_day[obs_date]:
            by_day[obs_date] = price

    slots: Dict[str, Optional[float]] = {}
    for days_ago in HISTORY_SLOT_DAYS_AGO:
        target_date = today.fromordinal(today.toordinal() - days_ago)
        slots[f"d{days_ago}"] = by_day.get(target_date)

    def _slot_key(days_ago: int) -> str:
        return f"d{days_ago}"

    d1_3 = [slots[_slot_key(n)] for n in (1, 2, 3) if slots[_slot_key(n)] is not None]
    d1_7 = [slots[_slot_key(n)] for n in (1, 2, 3, 4, 5, 6, 7) if slots[_slot_key(n)] is not None]

    ma_3d = (sum(d1_3) / len(d1_3)) if d1_3 else None
    ma_7d = (sum(d1_7) / len(d1_7)) if d1_7 else None

    return {"slots": slots, "ma_3d": ma_3d, "ma_7d": ma_7d}
