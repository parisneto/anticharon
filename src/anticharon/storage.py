"""CSV storage management with compact sliding window and cold-start padding."""

from pathlib import Path
from typing import Dict, List
from anticharon.models import PriceRecord

CSV_HEADER = "model,last_updated,current_price_1m,ma_3d,ma_7d,d1,d2,d3,d4,d5,d6,d7,d15,d30"


def read_history(history_path: Path) -> Dict[str, PriceRecord]:
    """Read historical price records from CSV file."""
    history: Dict[str, PriceRecord] = {}
    if not history_path.exists():
        return history

    try:
        with open(history_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            if len(lines) <= 1:
                return history

            for line in lines[1:]:
                parts = [p.strip() for p in line.split(",")]
                if len(parts) >= 14:
                    model = parts[0]
                    last_updated = parts[1]
                    current = float(parts[2])
                    ma_3d = float(parts[3])
                    ma_7d = float(parts[4])
                    prices = [float(p) for p in parts[5:14]]  # d1..d7, d15, d30
                    history[model] = PriceRecord(
                        model=model,
                        last_updated=last_updated,
                        current=current,
                        ma_3d=ma_3d,
                        ma_7d=ma_7d,
                        prices=prices
                    )
    except Exception:
        pass
    return history


def write_history(records: List[List[str | float]], history_path: Path) -> None:
    """Persist updated price records to CSV file."""
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with open(history_path, "w", encoding="utf-8") as f:
        f.write(CSV_HEADER + "\n")
        for rec in records:
            formatted = [
                f"{round(x, 6):.6f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)
                for x in rec
            ]
            f.write(",".join(formatted) + "\n")
