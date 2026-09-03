"""Core tracking and price calculation engine for Anticharon."""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import requests

from anticharon.analytics import calculate_model_analytics
from anticharon.config import load_config, get_history_path, get_config_path
from anticharon.hermes import get_hermes_models, sync_hermes_to_config
from anticharon.models import ModelPrice, PriceWarning, TrackerResult, HermesIntegrationStatus
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
    timeout: float = 10.0,
    hermes_config_path: Optional[str | Path] = None,
    no_hermes: bool = False,
    enable_analytics: bool = False,
    hints_enabled: bool = False
) -> TrackerResult:
    """Execute price tracker workflow."""
    cfg_path = config_path or get_config_path()
    cfg = load_config(cfg_path)
    hist_path = history_path or get_history_path()
    history = read_history(hist_path)

    # Hermes auto-detection & synchronization
    hermes_status: Optional[HermesIntegrationStatus] = None
    if not no_hermes:
        hermes_info = get_hermes_models(custom_path=hermes_config_path)
        if hermes_info:
            hermes_status = HermesIntegrationStatus(
                detected=True,
                source=hermes_info.get("source"),
                method=hermes_info.get("method", "file_grep"),
                models_count=len(hermes_info.get("all_models", [])),
                warning=None
            )
            # Sync to shortlist config unless dry_run
            if not dry_run:
                sync_hermes_to_config(hermes_info, config_path=cfg_path, dry_run=False)
                cfg = load_config(cfg_path)
            # Use hermes models for current tracking session
            shortlist = hermes_info.get("all_models", [])
        else:
            hermes_status = HermesIntegrationStatus(
                detected=False,
                source=None,
                method="standalone",
                models_count=0,
                warning="Hermes configuration not detected. Operating in standalone mode."
            )
            shortlist = cfg.get("shortlist", [])
    else:
        hermes_status = HermesIntegrationStatus(
            detected=False,
            source=None,
            method="standalone",
            models_count=0,
            warning=None
        )
        shortlist = cfg.get("shortlist", [])

    models_api = fetch_openrouter_models(timeout=timeout)

    w_in = cfg.get("weight_prompt", 0.9971)
    w_out = cfg.get("weight_completion", 0.0029)
    threshold = cfg.get("spike_threshold_pct", 20.0)
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
        if enable_analytics:
            cand = {p.model: p.price_1m for p in prices_shortlist}
            c_def = shortlist[0] if shortlist else None
            for p in prices_shortlist:
                if p.model in history:
                    p.analytics = calculate_model_analytics(
                        model_id=p.model,
                        current_price=p.price_1m,
                        history_prices=history[p.model].prices,
                        candidate_prices=cand,
                        current_default=c_def
                    )
        return TrackerResult(
            status="success",
            timestamp=now_iso,
            fallback=True,
            prices_shortlist=prices_shortlist,
            price_warnings=[],
            storage_path=str(hist_path),
            config_path=str(cfg_path),
            hermes_integration=hermes_status,
            analytics_mode=enable_analytics,
            hints_enabled=hints_enabled
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

    if enable_analytics:
        if updated_records:
            history_prices_map = {row[0]: row[5:] for row in updated_records}
        else:
            history_prices_map = {m: r.prices for m, r in history.items()}

        cand = {p.model: p.price_1m for p in prices_shortlist}
        c_def = shortlist[0] if shortlist else None
        for p in prices_shortlist:
            if p.model in history_prices_map:
                p.analytics = calculate_model_analytics(
                    model_id=p.model,
                    current_price=p.price_1m,
                    history_prices=history_prices_map[p.model],
                    candidate_prices=cand,
                    current_default=c_def
                )

    return TrackerResult(
        status="success",
        timestamp=now_iso,
        fallback=False,
        prices_shortlist=prices_shortlist,
        price_warnings=warnings,
        storage_path=str(hist_path),
        config_path=str(cfg_path),
        hermes_integration=hermes_status,
        analytics_mode=enable_analytics,
        hints_enabled=hints_enabled
    )
