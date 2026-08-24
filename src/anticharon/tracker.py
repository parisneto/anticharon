"""Core tracking and price calculation engine for Anticharon."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from anticharon.config import load_config, get_history_path, get_config_path
from anticharon.models import ModelPrice, PriceWarning, TrackerResult
from anticharon.storage import read_history, write_history

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def fetch_openrouter_models(timeout: float = 10.0) -> Dict[str, Any]:
    """Fetch all active model records from OpenRouter public API."""
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return {m["id"]: m for m in data if "id" in m}
    except Exception as e:
        print(f"[WARN] Failed to query OpenRouter API ({e}). Falling back to cached history.", file=sys.stderr)
        return {}


def run_tracker(
    dry_run: bool = False,
    config_path: Optional[Path] = None,
    history_path: Optional[Path] = None,
    timeout: float = 10.0
) -> TrackerResult:
    """Execute price tracker workflow."""
    cfg = load_config(config_path or get_config_path())
    hist_path = history_path or get_history_path()
    history = read_history(hist_path)
    models_api = fetch_openrouter_models(timeout=timeout)

    w_in = cfg.get("weight_prompt", 0.9922)
    w_out = cfg.get("weight_completion", 0.0078)
    threshold = cfg.get("spike_threshold_pct", 20.0)
    shortlist = cfg.get("shortlist", [])
    now_iso = datetime.now(timezone.utc).isoformat()

    # Fallback mode when API query returns empty
    if not models_api and history:
        prices_shortlist = []
        for model_id in shortlist:
            if model_id in history:
                rec = history[model_id]
                delta_7d_pct = ((rec.current - rec.ma_7d) / rec.ma_7d) * 100 if rec.ma_7d > 0 else 0.0
                prices_shortlist.append(ModelPrice(
                    model=model_id,
                    price_1m=rec.current,
                    ma_7d=rec.ma_7d,
                    ma_3d=rec.ma_3d,
                    change_vs_7d_pct=delta_7d_pct
                ))
        prices_shortlist.sort(key=lambda x: x.price_1m)
        return TrackerResult(
            status="success",
            timestamp=now_iso,
            fallback=True,
            prices_shortlist=prices_shortlist,
            price_warnings=[]
        )

    updated_records = []
    prices_shortlist = []
    warnings = []

    for model_id in shortlist:
        api_data = models_api.get(model_id)
        if not api_data:
            # Check if permalink alias exists without full date tag or similar
            matching_key = next((k for k in models_api if k.startswith(model_id)), None)
            if matching_key:
                api_data = models_api[matching_key]

        if not api_data:
            continue

        pricing = api_data.get("pricing", {})
        try:
            p_in = float(pricing.get("prompt", 0)) * 1_000_000
            p_out = float(pricing.get("completion", 0)) * 1_000_000
        except (ValueError, TypeError):
            p_in, p_out = 0.0, 0.0

        current_1m = (p_in * w_in) + (p_out * w_out)

        # Retrieve prior history or handle cold start
        if model_id in history:
            prev_prices = history[model_id].prices
            new_prices = [current_1m] + prev_prices[:8]
        else:
            # Cold-start: replicate initial price across the window
            new_prices = [current_1m] * 9

        ma_3d = sum(new_prices[:3]) / 3
        ma_7d = sum(new_prices[:7]) / 7

        delta_7d_pct = ((current_1m - ma_7d) / ma_7d) * 100 if ma_7d > 0 else 0.0

        # Anomaly / Spikes / Drops detection
        if delta_7d_pct >= threshold:
            warnings.append(PriceWarning(
                type="PRICE_SPIKE",
                model=model_id,
                message=f"Model {model_id} price spiked +{delta_7d_pct:.1f}% vs 7-day MA. Current: ${current_1m:.5f}/1M."
            ))
        elif delta_7d_pct <= -threshold:
            warnings.append(PriceWarning(
                type="PRICE_DROP",
                model=model_id,
                message=f"Model {model_id} price dropped {abs(delta_7d_pct):.1f}% vs 7-day MA. Current: ${current_1m:.5f}/1M."
            ))

        prices_shortlist.append(ModelPrice(
            model=model_id,
            price_1m=current_1m,
            ma_7d=ma_7d,
            ma_3d=ma_3d,
            change_vs_7d_pct=delta_7d_pct,
            prompt_price_raw=p_in,
            completion_price_raw=p_out
        ))

        updated_records.append([model_id, now_iso, current_1m, ma_3d, ma_7d] + new_prices)

    # Persist records unless dry_run
    if not dry_run and updated_records:
        write_history(updated_records, hist_path)

    # Sort shortlist by cheapest price
    prices_shortlist.sort(key=lambda x: x.price_1m)

    # Check if lowest-cost option differs from default (first in shortlist)
    if shortlist:
        current_default = shortlist[0]
        if prices_shortlist and prices_shortlist[0].model != current_default:
            cheapest = prices_shortlist[0]
            warnings.append(PriceWarning(
                type="BEST_OPTION_CHANGED",
                current_default=current_default,
                suggested_cheapest=cheapest.model,
                message=f"Model {cheapest.model} (${cheapest.price_1m:.5f}/1M) is cheaper than configured default {current_default}."
            ))

    return TrackerResult(
        status="success",
        timestamp=now_iso,
        fallback=False,
        prices_shortlist=prices_shortlist,
        price_warnings=warnings
    )
