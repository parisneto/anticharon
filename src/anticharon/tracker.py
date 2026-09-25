"""Core tracking and price calculation engine for Anticharon.

Implements the cache-aware, provider-routable pricing model from
docs/plans/pricing-engine-v2/PLAN.md: advertised (bulk catalog headline),
effective (3-component cache-aware blend against the cheapest real endpoint),
and policy (same blend restricted to policy-compliant endpoints, ZDR to
start) are three distinct numbers, never collapsed into one. The legacy
2-component gross formula is removed as an independent downstream path.
"""

import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from anticharon.analytics import calculate_model_analytics
from anticharon.config import (
    default_model,
    get_config_path,
    get_history_path,
    load_config,
)
from anticharon.hermes import (
    get_hermes_models,
    hermes_detection_messages,
    shortlist_write_message,
    sync_hermes_to_config,
)
from anticharon.models import (
    AgentMessage,
    HermesIntegrationStatus,
    ModelPrice,
    PricePoint,
    PriceWarning,
    TrackerResult,
)
from anticharon.pricing import (
    blended_rate_1m,
    derive_cache_hit_rate,
    is_valid_listed_price,
    parse_required_price_1m,
    resolve_cache_read_price_1m,
)
from anticharon.storage import (
    derive_history_window,
    get_alerts_path,
    get_effective_prices_path,
    is_model_backfill_stale,
    read_alerts,
    read_effective_prices,
    read_history,
    write_alerts,
    write_effective_prices,
    write_history,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
# Internal, unauthenticated frontend routes -- no formal SLA, same graceful-degradation
# contract as every other network call in this codebase (see PLAN.md "Policy (ZDR)
# pricing data source" and "28-Day Backfill").
OPENROUTER_ENDPOINT_STATS_URL = "https://openrouter.ai/api/frontend/v1/stats/endpoint"
OPENROUTER_EFFECTIVE_PRICING_URL = "https://openrouter.ai/api/frontend/v1/stats/effective-pricing"

PREVIEW_ONLY_RUN_MESSAGE = AgentMessage(
    "info", "PREVIEW_ONLY",
    "Dry run: prices were fetched and computed for this response only; nothing was persisted "
    "(history.csv, effective_prices.json and shortlist.json are unchanged).",
    action={"mcp": "run_prices()", "cli": "anticharon run"},
)
API_FALLBACK_MESSAGE = AgentMessage(
    "warning", "API_FALLBACK",
    "OpenRouter API was unreachable; showing the last cached prices from history.csv.",
    action={"mcp": "retry run_prices() later", "cli": "retry anticharon run later"},
)
DATA_STALE_MESSAGE = AgentMessage(
    "warning", "DATA_STALE",
    "The latest locally stored price observation is older than today; run to refresh.",
    action={"mcp": "run_prices()", "cli": "anticharon run"},
)
# Alert types recomputed fresh on every read/write of alerts.json rather than
# copied forward from a prior run: BEST_OPTION_CHANGED is cross-model and is
# always rebuilt from the currently stored prices (D-22 rule 1); POLICY_* is
# never persisted at all (D-28).
_NEVER_PERSISTED_ALERT_TYPES = frozenset({"POLICY_UNROUTABLE", "POLICY_UNKNOWN"})
_CROSS_MODEL_ALERT_TYPE = "BEST_OPTION_CHANGED"


def fetch_openrouter_models(timeout: float = 10.0) -> dict[str, Any]:
    """Fetch all active model records from OpenRouter public bulk catalog (advertised price/metadata).
    Graceful degradation: {} on any failure, including a wrong-typed nested `data`
    payload (e.g. not a list, or a list of non-dict entries) -- never raise past
    this function into a downstream consumer (PE2-006)."""
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not isinstance(data, list):
            return {}
        return {m["id"]: m for m in data if isinstance(m, dict) and "id" in m}
    except Exception as e:
        print(f"[WARN] Failed to query OpenRouter API ({e}). Falling back to cached history.", file=sys.stderr)
        return {}


def fetch_endpoint_policy_pricing(canonical_slug: str, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Per-endpoint effective/policy pricing + the real, unauthenticated ZDR signal
    (`provider_info.dataPolicy.retainsPrompts`) -- supersedes the public
    `/models/{slug}/endpoints` call for this project (live-verified: that call's
    `status` field reports 0/routable for everyone on an unauthenticated request).
    Graceful degradation: [] on any failure, including a wrong-typed nested `data`
    payload (e.g. a mapping instead of a list, or a list of non-dict entries) --
    never raise past this function into a downstream consumer (PE2-006)."""
    try:
        resp = requests.get(
            OPENROUTER_ENDPOINT_STATS_URL,
            params={
                "latencyMetric": "latency",
                "perfWorkload": "text_generation",
                "permaslug": canonical_slug,
                "variant": "standard",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not isinstance(data, list):
            return []
        return [ep for ep in data if isinstance(ep, dict)]
    except Exception:
        return []


def extract_endpoint_listed_prices_1m(endpoints: list[dict[str, Any]]) -> list[float]:
    """Extract each endpoint's own raw listed prompt price ($/1M) from
    `/stats/endpoint` data, skipping any endpoint with missing/malformed/
    sentinel pricing (PE2-002/PE2-005).

    Used by the PE2-005 live cross-validation canary: the bulk catalog's
    `advertised_prompt_1m` is definitionally one of the real routable
    endpoints' own listed price (OpenRouter's headline is never a fabricated
    number), so at least one entry in this list should exactly match it. If
    none do, that is a real early-warning signal that `/stats/endpoint`'s
    pricing shape or semantics have drifted from the bulk catalog's.
    """
    prices: list[float] = []
    for ep in endpoints:
        pricing = ep.get("pricing") or {}
        p_in = parse_required_price_1m(pricing, "prompt")
        if p_in is not None and is_valid_listed_price(p_in):
            prices.append(p_in)
    return prices


def fetch_effective_pricing_history(canonical_slug: str, timeout: float = 10.0) -> dict[str, Any]:
    """28-day backfill source. `range=1m` is required for ~30 days of daily
    observations -- live-verified: the bare/default call (no `range`) only
    returns the last 8 days. Graceful degradation: {} on failure, or when the
    model has no persistent history of its own (e.g. a `~`-prefixed router
    alias like `~deepseek/deepseek-pro-latest`, live-verified to return an
    empty-but-200-OK payload since "latest" has no fixed permaslug identity).
    Also degrades to {} for a wrong-typed nested `data` payload (e.g. a list
    instead of a mapping) -- never raise past this function into
    `_reduce_to_daily_observations` (PE2-006)."""
    try:
        resp = requests.get(
            OPENROUTER_EFFECTIVE_PRICING_URL,
            params={"permaslug": canonical_slug, "shape": "v7", "variant": "standard", "range": "1m"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}


def _endpoint_blended_rate_1m(
    endpoint: dict[str, Any], w_uncached: float, w_cached: float, w_completion: float
) -> float | None:
    """Cache-aware blended $/1M for one endpoint, or None if its pricing is
    missing/invalid. PE2-002: `prompt`/`completion` are required fields --
    a missing/blank/malformed value returns None (endpoint unusable), never
    a fabricated $0 (see `parse_required_price_1m`)."""
    pricing = endpoint.get("pricing") or {}
    p_in = parse_required_price_1m(pricing, "prompt")
    p_out = parse_required_price_1m(pricing, "completion")
    if p_in is None or p_out is None:
        return None
    if not (is_valid_listed_price(p_in) and is_valid_listed_price(p_out)):
        return None

    cache_read_raw = pricing.get("input_cache_read")
    try:
        p_cache = float(cache_read_raw) * 1_000_000 if cache_read_raw not in (None, "") else None
    except (ValueError, TypeError):
        p_cache = None
    p_cache = resolve_cache_read_price_1m(p_in, p_cache)

    return blended_rate_1m(p_in, p_cache, p_out, w_uncached, w_cached, w_completion)


def resolve_policy_pricing(
    endpoints: list[dict[str, Any]],
    w_uncached: float,
    w_cached: float,
    w_completion: float,
    zdr_only: bool,
) -> dict[str, Any]:
    """effective_price_1m = cheapest endpoint's blended rate (always, when endpoint
    data is available). policy_price_1m/is_policy_routable/excluded_providers are
    only populated when `zdr_only` is active -- an inactive policy filter means
    there's no policy price at all (see PLAN.md "Core pricing semantics")."""
    rates: list[float] = []
    zdr_rates: list[float] = []
    excluded_providers: list[str] = []

    for ep in endpoints:
        rate = _endpoint_blended_rate_1m(ep, w_uncached, w_cached, w_completion)
        if rate is None:
            continue
        rates.append(rate)
        if zdr_only:
            data_policy = (ep.get("provider_info") or {}).get("dataPolicy") or {}
            if data_policy.get("retainsPrompts") is False:
                zdr_rates.append(rate)
            else:
                excluded_providers.append(ep.get("provider_name") or ep.get("provider_slug") or "unknown")

    result: dict[str, Any] = {
        "effective_price_1m": min(rates) if rates else None,
        "policy_price_1m": None,
        "is_policy_routable": None,
        "excluded_providers": [],
    }
    # PE2-002/PE2-003: gate on `rates` (at least one endpoint actually produced a
    # usable price), not the raw `endpoints` list -- a non-empty `endpoints` list
    # where every entry has missing/malformed pricing (PE2-002) must resolve to
    # policy-unknown here too, not "confirmed unroutable." Using `endpoints`
    # previously conflated "we have no valid pricing data to judge routability
    # from" with "we checked, and no endpoint is ZDR-compliant."
    if zdr_only and rates:
        result["is_policy_routable"] = len(zdr_rates) > 0
        result["policy_price_1m"] = min(zdr_rates) if zdr_rates else None
        result["excluded_providers"] = excluded_providers
    return result


def _reduce_to_daily_observations(history_data: dict[str, Any], w_completion: float) -> list[dict[str, Any]]:
    """Collapse the effective-pricing route's per-endpoint daily input/output series
    into one blended $/1M observation per calendar day (the cheapest endpoint that
    day). OpenRouter's per-endpoint series is already cache-weighted by that
    provider's real traffic that day -- only the input/output combination is ours
    to apply, via the locally calibrated `weight_completion` split."""
    input_series = history_data.get("inputChartData") or []
    output_series = history_data.get("outputChartData") or []
    output_by_date: dict[str, dict[str, float]] = {
        entry.get("x", "").split(" ")[0]: (entry.get("y") or {}) for entry in output_series
    }

    observations: list[dict[str, Any]] = []
    for entry in input_series:
        date_str = entry.get("x", "").split(" ")[0]
        if not date_str:
            continue
        input_by_endpoint = entry.get("y") or {}
        output_by_endpoint = output_by_date.get(date_str, {})

        day_rates = []
        for endpoint_id, input_price in input_by_endpoint.items():
            output_price = output_by_endpoint.get(endpoint_id)
            if output_price is None:
                continue
            try:
                day_rates.append(float(input_price) * (1 - w_completion) + float(output_price) * w_completion)
            except (ValueError, TypeError):
                continue

        if day_rates:
            observations.append({"date": date_str, "effective_price_1m": min(day_rates)})

    return observations


def sync_effective_prices_for_model(
    model_id: str,
    canonical_slug: str,
    store: dict[str, Any],
    w_completion: float,
    timeout: float,
    now: datetime | None = None,
) -> None:
    """Backfill/refresh one model's granular observations in `store`, in place,
    respecting the store's own staleness policy (independent of history.csv's
    per-run cadence). Mutates `store[model_id]`."""
    if not is_model_backfill_stale(store, model_id, now=now):
        return

    now = now or datetime.now(timezone.utc)
    history_data = fetch_effective_pricing_history(canonical_slug, timeout=timeout)
    new_observations = _reduce_to_daily_observations(history_data, w_completion)

    entry = store.get(model_id) or {"canonical_slug": canonical_slug, "observations": []}
    entry.setdefault("first_seen", now.date().isoformat())
    entry["canonical_slug"] = canonical_slug
    entry["last_synced"] = now.isoformat()
    if new_observations:
        # Only overwrite when the fetch actually returned data -- a transient
        # failure or a router alias with no fixed history must not destroy
        # previously accumulated real observations.
        entry["observations"] = new_observations
    store[model_id] = entry


def tracking_days_elapsed(store: dict[str, Any], model_id: str, today: date) -> int | None:
    """Elapsed calendar days since a model was first tracked, per the granular
    store's `first_seen` -- drives analytics.py's NEWLY_TRACKED threshold.
    `None` (unknown) when the model has no store entry yet."""
    entry = store.get(model_id)
    if not entry or not entry.get("first_seen"):
        return None
    try:
        first_seen = date.fromisoformat(entry["first_seen"])
    except (ValueError, TypeError):
        return None
    return (today - first_seen).days


def _parse_record_date(last_updated: str) -> date | None:
    try:
        return datetime.fromisoformat(last_updated).date()
    except (ValueError, TypeError):
        return None


def _price_record_row(rec: Any) -> list[Any]:
    """Reconstruct a `write_history` row from a stored `PriceRecord`, so a
    filtered/partial persist can carry forward every other model's row
    unchanged (MCP-10: no shortlisted model's history is ever dropped)."""
    return [
        rec.model, rec.last_updated, rec.effective_price_1m, rec.advertised_prompt_1m,
        rec.advertised_completion_1m, rec.ma_3d, rec.ma_7d, *rec.prices,
    ]


def _price_warning_from_dict(d: dict[str, Any]) -> PriceWarning:
    return PriceWarning(
        type=d["type"], message=d["message"], model=d.get("model"),
        current_default=d.get("current_default"), suggested_cheapest=d.get("suggested_cheapest"),
        policy=d.get("policy"), excluded_providers=d.get("excluded_providers"), reason=d.get("reason"),
    )


def _recompute_best_option_changed(price_map: dict[str, float], current_default: str | None) -> PriceWarning | None:
    """Cross-model alert, always derived from the unconstrained effective price
    (never a ZDR-ranked one -- D-28 policy prices are never persisted)."""
    if not current_default or current_default not in price_map or not price_map:
        return None
    cheapest_model = min(price_map, key=price_map.get)
    if cheapest_model == current_default:
        return None
    cheapest_price = price_map[cheapest_model]
    return PriceWarning(
        type=_CROSS_MODEL_ALERT_TYPE,
        current_default=current_default,
        suggested_cheapest=cheapest_model,
        message=f"Model {cheapest_model} (${cheapest_price:.5f}/1M) is cheaper than configured default {current_default}.",
    )


def _persist_alerts(
    warnings: list[PriceWarning],
    records_by_model: dict[str, list[Any]],
    full_shortlist: list[str],
    current_default: str | None,
    now_iso: str,
    model_id: str | None,
    alerts_path: Path,
) -> None:
    """Write alerts.json (D-22): the run's per-model alerts plus a freshly
    recomputed cross-model `BEST_OPTION_CHANGED`. A filtered `run --model X`
    replaces only X's per-model alerts and the cross-model alert, keeping
    every other model's persisted alerts (Rule 1)."""
    price_map = {m: records_by_model[m][2] for m in full_shortlist if m in records_by_model}
    recomputed_best = _recompute_best_option_changed(price_map, current_default)
    fresh_per_model = [w.to_dict() for w in warnings if w.type not in _NEVER_PERSISTED_ALERT_TYPES | {_CROSS_MODEL_ALERT_TYPE}]

    if model_id is None:
        price_warnings = fresh_per_model
    else:
        existing = read_alerts(alerts_path).get("price_warnings", [])
        kept = [w for w in existing if w.get("type") != _CROSS_MODEL_ALERT_TYPE and w.get("model") != model_id]
        price_warnings = kept + fresh_per_model

    if recomputed_best is not None:
        price_warnings.append(recomputed_best.to_dict())

    write_alerts({
        "timestamp": now_iso,
        "default_model": current_default,
        "data_source": "live_api",
        "price_warnings": price_warnings,
    }, alerts_path)


def run_tracker(
    dry_run: bool = False,
    config_path: Path | None = None,
    history_path: Path | None = None,
    timeout: float = 10.0,
    hermes_config_path: str | Path | None = None,
    no_hermes: bool = False,
    enable_analytics: bool = False,
    hints_enabled: bool = False,
    zdr_only: bool = False,
    model_id: str | None = None,
    force: bool = False,
) -> TrackerResult:
    """Execute price tracker workflow (D-19 `run`/`run_prices`: the only
    fetch-and-write path). `force` re-fetches shortlisted models even if
    already updated today (D-3, D-18b); without it, a full-shortlist run
    reuses today's already-persisted price for a model instead of refetching
    it (same-day rule, D-18/MCP-10)."""
    cfg_path = config_path or get_config_path()
    cfg = load_config(cfg_path)
    if model_id is not None:
        target = model_id.strip()
        if target not in cfg.get("shortlist", []):
            return TrackerResult(
                status="refused", timestamp=datetime.now(timezone.utc).isoformat(),
                config_path=str(cfg_path), messages=[AgentMessage(
                    "error", "NOT_MONITORED", f"Model '{target}' is not in the configured shortlist.",
                    action={"mcp": "add_model(model_id)", "cli": f"anticharon model add {target}"}, model=target,
                )],
            )
    hist_path = history_path or get_history_path()
    history = read_history(hist_path)
    effective_prices_path = get_effective_prices_path(hist_path.parent)
    effective_store = read_effective_prices(effective_prices_path)

    # Hermes auto-detection & synchronization
    hermes_status: HermesIntegrationStatus | None = None
    messages: list[AgentMessage] = []
    if not no_hermes:
        hermes_info = get_hermes_models(custom_path=hermes_config_path)
        if hermes_info:
            cfg = load_config(cfg_path, legacy_source="hermes")
            persisted_entries = cfg.get("_shortlist_entries", [])
            # An incomplete detection is never allowed to shrink the shortlist
            # or to drive this run's tracking set (Issue #4).
            incomplete = hermes_info.get("detection", "complete") != "complete"
            hermes_status = HermesIntegrationStatus(
                detected=True,
                source=hermes_info.get("source"),
                method=hermes_info.get("method", "file_grep"),
                models_count=len(hermes_info.get("all_models", [])),
            )
            # Sync to shortlist config unless dry_run
            sync_message = None
            changed, merged_shortlist, _ = sync_hermes_to_config(hermes_info, config_path=cfg_path, dry_run=dry_run)
            if not dry_run:
                cfg = load_config(cfg_path)
                sync_message = shortlist_write_message(
                    changed, False, f"Hermes sync of {hermes_status.models_count} models"
                )
            elif not incomplete:
                manual_entries = [entry for entry in cfg.get("_shortlist_entries", []) if entry.get("source") != "hermes"]
                cfg["_shortlist_entries"] = [
                    {"model": slug, "source": "hermes", "order": order}
                    for order, slug in enumerate(hermes_info.get("all_models", []))
                ] + manual_entries
            # Divergence is judged against the shortlist as persisted after any sync (A2A-6).
            comparison_entries = persisted_entries if dry_run else cfg.get("_shortlist_entries", [])
            messages.extend(hermes_detection_messages(hermes_info, comparison_entries))
            if sync_message:
                messages.append(sync_message)
            # Use hermes models for current tracking session
            if incomplete:
                shortlist = cfg.get("shortlist", []) or hermes_info.get("all_models", [])
            else:
                shortlist = merged_shortlist
        else:
            hermes_status = HermesIntegrationStatus(
                detected=False,
                source=None,
                method="standalone",
                models_count=0,
            )
            messages.extend(hermes_detection_messages(None, []))
            shortlist = cfg.get("shortlist", [])
    else:
        hermes_status = HermesIntegrationStatus(
            detected=False,
            source=None,
            method="standalone",
            models_count=0,
        )
        shortlist = cfg.get("shortlist", [])
    if model_id is not None:
        shortlist = [model_id.strip()]
    if dry_run:
        messages.append(PREVIEW_ONLY_RUN_MESSAGE)
    current_default = default_model(cfg.get("_shortlist_entries", []))
    entry_by_model = {entry["model"]: entry for entry in cfg.get("_shortlist_entries", [])}
    if current_default is None:
        messages.append(AgentMessage("info", "NO_DEFAULT",
            "No default model is set; default-based alerts are off. Set one with model add --default."))

    models_api = fetch_openrouter_models(timeout=timeout)

    w_uncached = cfg.get("weight_uncached_prompt", 0.232622)
    w_cached = cfg.get("weight_cached_prompt", 0.764478)
    w_completion = cfg.get("weight_completion", 0.0029)
    # PE2-008: cache_hit_rate_used (display-only) is the real prompt cache-hit
    # rate, NOT weight_cached_prompt itself -- see derive_cache_hit_rate's
    # docstring for the derivation.
    cache_hit_rate = derive_cache_hit_rate(w_uncached, w_cached)
    threshold = cfg.get("spike_threshold_pct", 20.0)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    today = now.date()

    # Fallback mode when API query returns empty
    if not models_api and history:
        prices_shortlist = []
        for fallback_model_id in shortlist:
            if fallback_model_id in history:
                rec = history[fallback_model_id]
                delta_7d_pct = ((rec.effective_price_1m - rec.ma_7d) / rec.ma_7d) * 100 if rec.ma_7d > 0 else 0.0
                prices_shortlist.append(ModelPrice(
                    model=fallback_model_id,
                    price_1m=rec.effective_price_1m,
                    ma_7d=rec.ma_7d,
                    ma_3d=rec.ma_3d,
                    change_vs_7d_pct=delta_7d_pct,
                    price=PricePoint(
                        advertised_prompt_1m=rec.advertised_prompt_1m,
                        advertised_completion_1m=rec.advertised_completion_1m,
                        effective_price_1m=rec.effective_price_1m,
                        cache_hit_rate_used=cache_hit_rate,
                    ),
                    canonical_slug=(effective_store.get(fallback_model_id) or {}).get("canonical_slug"),
                    source=entry_by_model.get(fallback_model_id, {}).get("source"),
                    is_default=fallback_model_id == current_default,
                ))
        prices_shortlist.sort(key=lambda x: x.price_1m)
        if enable_analytics:
            cand = {p.model: p.price_1m for p in prices_shortlist}
            c_def = current_default
            min_tracking_days = cfg.get("min_tracking_days_for_profile", 14)
            for p in prices_shortlist:
                if p.model in history:
                    p.analytics = calculate_model_analytics(
                        model_id=p.model,
                        current_price=p.price_1m,
                        history_prices=history[p.model].prices,
                        candidate_prices=cand,
                        current_default=c_def,
                        min_tracking_days_for_profile=min_tracking_days,
                        tracking_days_elapsed=tracking_days_elapsed(effective_store, p.model, today),
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
            hints_enabled=hints_enabled,
            messages=[API_FALLBACK_MESSAGE, *messages],
        )

    updated_records = []
    prices_shortlist = []
    warnings = []

    for tracked_model_id in shortlist:
        existing_record = history.get(tracked_model_id)
        reuse_existing = (
            not force and not zdr_only and model_id is None
            and existing_record is not None
            and _parse_record_date(existing_record.last_updated) == today
        )
        if reuse_existing:
            # Same-day rule (D-18/MCP-10): this model was already refreshed
            # today -- reuse its persisted price instead of a fresh per-model
            # endpoint fetch. It keeps its existing history.csv row (no entry
            # in `updated_records`), but still counts toward this run's
            # display and cross-model alert computation.
            reuse_delta_7d_pct = (
                (existing_record.effective_price_1m - existing_record.ma_7d) / existing_record.ma_7d * 100
                if existing_record.ma_7d > 0 else 0.0
            )
            if reuse_delta_7d_pct >= threshold:
                warnings.append(PriceWarning(
                    type="PRICE_SPIKE", model=tracked_model_id,
                    message=f"Model {tracked_model_id} price spiked +{reuse_delta_7d_pct:.1f}% vs 7-day MA. Current: ${existing_record.effective_price_1m:.5f}/1M."
                ))
            elif reuse_delta_7d_pct <= -threshold:
                warnings.append(PriceWarning(
                    type="PRICE_DROP", model=tracked_model_id,
                    message=f"Model {tracked_model_id} price dropped {abs(reuse_delta_7d_pct):.1f}% vs 7-day MA. Current: ${existing_record.effective_price_1m:.5f}/1M."
                ))
            prices_shortlist.append(ModelPrice(
                model=tracked_model_id,
                price_1m=existing_record.effective_price_1m,
                ma_7d=existing_record.ma_7d,
                ma_3d=existing_record.ma_3d,
                change_vs_7d_pct=reuse_delta_7d_pct,
                prompt_price_raw=existing_record.advertised_prompt_1m,
                completion_price_raw=existing_record.advertised_completion_1m,
                price=PricePoint(
                    advertised_prompt_1m=existing_record.advertised_prompt_1m,
                    advertised_completion_1m=existing_record.advertised_completion_1m,
                    effective_price_1m=existing_record.effective_price_1m,
                    cache_hit_rate_used=cache_hit_rate,
                ),
                canonical_slug=(effective_store.get(tracked_model_id) or {}).get("canonical_slug"),
                source=entry_by_model.get(tracked_model_id, {}).get("source"),
                is_default=tracked_model_id == current_default,
            ))
            continue

        api_data = models_api.get(tracked_model_id)
        if not api_data:
            messages.append(AgentMessage("warning", "NO_EXACT_MATCH",
                f"Model '{tracked_model_id}' is in the shortlist but has no exact catalog entry; it was skipped.",
                action={"mcp": f"discover_models(query=\"{tracked_model_id}\")", "cli": f"anticharon model discover \"{tracked_model_id}\""}, model=tracked_model_id))
            continue

        # PE2-002: prompt/completion are required bulk-catalog fields -- a
        # missing/blank/malformed value must skip the model entirely, never
        # fabricate a $0 advertised price (live-verified 2026-09-17: every
        # real catalog entry, including :free models, always includes both
        # keys explicitly; see parse_required_price_1m).
        pricing = api_data.get("pricing", {})
        advertised_prompt_1m = parse_required_price_1m(pricing, "prompt")
        advertised_completion_1m = parse_required_price_1m(pricing, "completion")
        if advertised_prompt_1m is None or advertised_completion_1m is None:
            messages.append(AgentMessage("warning", "PRICE_UNAVAILABLE",
                f"Pricing is unavailable for shortlisted model '{tracked_model_id}'; it was skipped.", model=tracked_model_id))
            continue

        if not (is_valid_listed_price(advertised_prompt_1m) and is_valid_listed_price(advertised_completion_1m)):
            # Sentinel/non-priced model (e.g. a meta-router like openrouter/auto-beta) --
            # skip rather than let a negative sentinel masquerade as "cheapest".
            messages.append(AgentMessage("warning", "PRICE_INVALID",
                f"Catalog pricing for shortlisted model '{tracked_model_id}' is invalid; it was skipped.", model=tracked_model_id))
            continue

        canonical_slug = api_data.get("canonical_slug") or tracked_model_id

        endpoints = fetch_endpoint_policy_pricing(canonical_slug, timeout=timeout)
        policy_result = resolve_policy_pricing(endpoints, w_uncached, w_cached, w_completion, zdr_only)

        if policy_result["effective_price_1m"] is not None:
            effective_price_1m = policy_result["effective_price_1m"]
        else:
            # Graceful degradation: the internal per-endpoint route failed or returned
            # nothing usable -- fall back to the bulk catalog's own headline pricing
            # blended with the calibrated weights (still cache-aware, just not
            # provider-routing-aware), rather than crashing or guessing zero.
            cache_read_raw = pricing.get("input_cache_read")
            try:
                p_cache = float(cache_read_raw) * 1_000_000 if cache_read_raw not in (None, "") else None
            except (ValueError, TypeError):
                p_cache = None
            p_cache = resolve_cache_read_price_1m(advertised_prompt_1m, p_cache)
            effective_price_1m = blended_rate_1m(
                advertised_prompt_1m, p_cache, advertised_completion_1m, w_uncached, w_cached, w_completion
            )

        policy_price_1m = policy_result["policy_price_1m"]
        is_policy_routable = policy_result["is_policy_routable"]

        if zdr_only and is_policy_routable is False:
            warnings.append(PriceWarning(
                type="POLICY_UNROUTABLE",
                model=tracked_model_id,
                policy="zdr",
                excluded_providers=policy_result["excluded_providers"],
                reason="No ZDR-compliant endpoint (dataPolicy.retainsPrompts=false) is currently routable.",
                message=f"Model {tracked_model_id} has no ZDR-compliant endpoint; policy price unavailable."
            ))
        elif zdr_only and is_policy_routable is None:
            # PE2-003: policy-unknown (the internal per-endpoint route failed, returned
            # no usable pricing, or genuinely reported zero endpoints) must be surfaced
            # explicitly, not silently conflated with confirmed noncompliance -- and per
            # PLAN.md's graceful-degradation rule, treated as routable-by-default for
            # ranking (see _rank_price_1m below), not excluded.
            warnings.append(PriceWarning(
                type="POLICY_UNKNOWN",
                model=tracked_model_id,
                policy="zdr",
                reason="ZDR compliance could not be determined (endpoint data unavailable); "
                       "falling back to the unconstrained effective price for ranking.",
                message=f"Model {tracked_model_id}'s ZDR compliance is unknown; treating as routable by default."
            ))

        # PE2-001 fix: price_1m (ModelPrice's sort/chart/delta key) is ALWAYS the
        # unconstrained effective price -- never replaced by the policy price, even
        # when zdr_only is active. effective_prices.json only ever stores unconstrained
        # effective observations, so ma_3d/ma_7d/delta_7d_pct/spike-drop comparisons
        # must stay on that same axis to remain like-for-like; mixing a
        # policy-constrained *current* price with an unconstrained *historical*
        # average would be an apples-to-oranges comparison
        # (docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001). The
        # policy-constrained price is still surfaced separately via
        # PricePoint.policy_price_1m and only overrides *ranking* for sort/
        # BEST_OPTION_CHANGED below, never price_1m itself.

        # 28-day backfill: refresh the granular per-model store per its own staleness
        # policy (independent of this run's cadence), then derive history.csv's
        # d1..d30/MA columns fresh from it -- this is what makes a same-day rerun
        # a no-op for d1..d30 (there is no "shift" left to double-apply).
        sync_effective_prices_for_model(
            tracked_model_id, canonical_slug, effective_store, w_completion, timeout, now=now
        )
        observations = (effective_store.get(tracked_model_id) or {}).get("observations", [])
        derived = derive_history_window(observations, today=today)
        ma_3d = derived["ma_3d"] if derived["ma_3d"] is not None else effective_price_1m
        ma_7d = derived["ma_7d"] if derived["ma_7d"] is not None else effective_price_1m
        slots = derived["slots"]

        delta_7d_pct = ((effective_price_1m - ma_7d) / ma_7d) * 100 if ma_7d > 0 else 0.0

        # Anomaly / Spikes / Drops detection
        if delta_7d_pct >= threshold:
            warnings.append(PriceWarning(
                type="PRICE_SPIKE",
                model=tracked_model_id,
                message=f"Model {tracked_model_id} price spiked +{delta_7d_pct:.1f}% vs 7-day MA. Current: ${effective_price_1m:.5f}/1M."
            ))
        elif delta_7d_pct <= -threshold:
            warnings.append(PriceWarning(
                type="PRICE_DROP",
                model=tracked_model_id,
                message=f"Model {tracked_model_id} price dropped {abs(delta_7d_pct):.1f}% vs 7-day MA. Current: ${effective_price_1m:.5f}/1M."
            ))

        prices_shortlist.append(ModelPrice(
            model=tracked_model_id,
            price_1m=effective_price_1m,
            ma_7d=ma_7d,
            ma_3d=ma_3d,
            change_vs_7d_pct=delta_7d_pct,
            prompt_price_raw=advertised_prompt_1m,
            completion_price_raw=advertised_completion_1m,
            price=PricePoint(
                advertised_prompt_1m=advertised_prompt_1m,
                advertised_completion_1m=advertised_completion_1m,
                effective_price_1m=effective_price_1m,
                policy_price_1m=policy_price_1m,
                is_policy_routable=is_policy_routable,
                cache_hit_rate_used=cache_hit_rate,
            ),
            canonical_slug=canonical_slug,
            source=entry_by_model.get(tracked_model_id, {}).get("source"),
            is_default=tracked_model_id == current_default,
        ))

        updated_records.append([
            tracked_model_id, now_iso, effective_price_1m, advertised_prompt_1m, advertised_completion_1m,
            ma_3d, ma_7d,
            slots["d1"], slots["d2"], slots["d3"], slots["d4"], slots["d5"], slots["d6"], slots["d7"],
            slots["d15"], slots["d30"],
        ])

    # Persist records unless dry_run. Merge onto every existing row (not just
    # this run's `updated_records`) so a filtered `run --model` -- or a
    # same-day reuse that skipped some models -- never drops another
    # shortlisted model's history (MCP-10, D-18c).
    if not dry_run and updated_records:
        records_by_model = {rec.model: _price_record_row(rec) for rec in history.values()}
        for row in updated_records:
            records_by_model[row[0]] = row
        write_history(list(records_by_model.values()), hist_path)
        write_effective_prices(effective_store, effective_prices_path)
        _persist_alerts(
            warnings, records_by_model, cfg.get("shortlist", []), current_default, now_iso, model_id,
            get_alerts_path(hist_path.parent),
        )

    # PE2-001/PE2-003 fix: rank by the policy-constrained price when a policy
    # filter is active. Three distinct cases per PLAN.md's graceful-degradation
    # rule ("policy-unknown, routable-by-default") -- confirmed-unroutable and
    # policy-unknown are NOT the same and must not share a ranking outcome:
    #   - policy_price_1m is set (confirmed routable): rank by it.
    #   - is_policy_routable is False (confirmed unroutable, real endpoint data
    #     checked, none ZDR-compliant): rank math.inf -- never "cheapest",
    #     never recommended via BEST_OPTION_CHANGED.
    #   - is_policy_routable is None (unknown -- endpoint data unavailable, or
    #     no PricePoint at all e.g. the offline-fallback path): routable-by-
    #     default -- rank by the unconstrained effective price, same as if no
    #     policy filter were active for this one model. The POLICY_UNKNOWN
    #     warning above already surfaces this uncertainty explicitly.
    # This ranking is display/recommendation-only -- it does not change
    # price_1m (always the unconstrained effective price) or persisted history.
    def _rank_price_1m(model_price: ModelPrice) -> float:
        if not zdr_only or not model_price.price:
            return model_price.price_1m
        if model_price.price.policy_price_1m is not None:
            return model_price.price.policy_price_1m
        if model_price.price.is_policy_routable is False:
            return math.inf
        return model_price.price_1m

    prices_shortlist.sort(key=_rank_price_1m)

    # Check if lowest-cost option differs from the explicitly configured default.
    if current_default and prices_shortlist and prices_shortlist[0].model != current_default:
        cheapest = prices_shortlist[0]
        cheapest_rank = _rank_price_1m(cheapest)
        # Never recommend a model that isn't actually the cheapest *routable*
        # option under the active policy filter (PE2-001).
        if cheapest_rank != math.inf:
            warnings.append(PriceWarning(
                type="BEST_OPTION_CHANGED",
                current_default=current_default,
                suggested_cheapest=cheapest.model,
                message=f"Model {cheapest.model} (${cheapest_rank:.5f}/1M) is cheaper than configured default {current_default}."
            ))

    if enable_analytics:
        if updated_records:
            history_prices_map = {row[0]: row[7:] for row in updated_records}
        else:
            history_prices_map = {m: r.prices for m, r in history.items()}

        cand = {p.model: p.price_1m for p in prices_shortlist}
        c_def = current_default
        min_tracking_days = cfg.get("min_tracking_days_for_profile", 14)
        for p in prices_shortlist:
            if p.model in history_prices_map:
                p.analytics = calculate_model_analytics(
                    model_id=p.model,
                    current_price=p.price_1m,
                    history_prices=history_prices_map[p.model],
                    candidate_prices=cand,
                    current_default=c_def,
                    min_tracking_days_for_profile=min_tracking_days,
                    tracking_days_elapsed=tracking_days_elapsed(effective_store, p.model, today),
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
        hints_enabled=hints_enabled,
        messages=messages,
    )


def _local_not_monitored_result(target: str, cfg_path: Path, hist_path: Path) -> TrackerResult:
    """`NOT_MONITORED` for a local read (`check`/`history`): `status:
    "not_monitored"`, level `warning` -- a normal result, not an error (D-1
    §3d: `not_monitored` is used only by local reads; `isError`/exit 1 are
    reserved for a filtered *live* run, e.g. `run --model` -- see the
    `refused` path in `run_tracker` above)."""
    return TrackerResult(
        status="not_monitored", timestamp=datetime.now(timezone.utc).isoformat(),
        config_path=str(cfg_path), storage_path=str(hist_path),
        messages=[AgentMessage(
            "warning", "NOT_MONITORED", f"Model '{target}' is not in the configured shortlist.",
            action={"mcp": "add_model(model_id)", "cli": f"anticharon model add {target}"}, model=target,
        )],
    )


def _local_hermes_snapshot(
    cfg_path: Path, cfg: dict[str, Any], hermes_config_path: str | Path | None, no_hermes: bool
) -> tuple[dict[str, Any], HermesIntegrationStatus, list[AgentMessage]]:
    """Local-only Hermes detection for `check`/`history`: no shortlist sync,
    just the detection status line and divergence/incomplete/not-detected
    messages (D-19 -- detection itself is a local subprocess/file read, not
    an OpenRouter network call). On a detection, reloads `cfg` with
    `legacy_source="hermes"` -- same as `run_tracker` -- so an untagged flat
    shortlist is interpreted as Hermes-sourced for the divergence check."""
    if no_hermes:
        return cfg, HermesIntegrationStatus(detected=False, source=None, method="standalone", models_count=0), []
    hermes_info = get_hermes_models(custom_path=hermes_config_path, prompt_if_missing=False)
    if hermes_info:
        cfg = load_config(cfg_path, legacy_source="hermes")
        status = HermesIntegrationStatus(
            detected=True, source=hermes_info.get("source"),
            method=hermes_info.get("method", "file_grep"),
            models_count=len(hermes_info.get("all_models", [])),
        )
    else:
        status = HermesIntegrationStatus(detected=False, source=None, method="standalone", models_count=0)
    messages = hermes_detection_messages(hermes_info, cfg.get("_shortlist_entries", []))
    return cfg, status, messages


def read_check_result(
    config_path: Path | None = None,
    history_path: Path | None = None,
    hermes_config_path: str | Path | None = None,
    no_hermes: bool = False,
    hints_enabled: bool = False,
    model_id: str | None = None,
) -> TrackerResult:
    """Local-only read of the latest persisted prices (D-19 `check`/`check_prices`):
    source is `history.csv` (the compact summary) and the alerts persisted by the
    last `run` in `alerts.json` -- never recomputed here (D-22). Makes no
    OpenRouter network call."""
    cfg_path = config_path or get_config_path()
    cfg = load_config(cfg_path)
    hist_path = history_path or get_history_path()

    target = model_id.strip() if model_id else None
    if target is not None and target not in cfg.get("shortlist", []):
        return _local_not_monitored_result(target, cfg_path, hist_path)

    cfg, hermes_status, messages = _local_hermes_snapshot(cfg_path, cfg, hermes_config_path, no_hermes)
    current_default = default_model(cfg.get("_shortlist_entries", []))
    if current_default is None:
        messages.append(AgentMessage("info", "NO_DEFAULT",
            "No default model is set; default-based alerts are off. Set one with model add --default."))

    entry_by_model = {entry["model"]: entry for entry in cfg.get("_shortlist_entries", [])}
    history = read_history(hist_path)
    effective_store = read_effective_prices(get_effective_prices_path(hist_path.parent))
    alerts_store = read_alerts(get_alerts_path(hist_path.parent))

    shortlist = [target] if target else cfg.get("shortlist", [])
    now = datetime.now(timezone.utc)
    today = now.date()

    prices_shortlist: list[ModelPrice] = []
    latest_date: date | None = None
    for slug in shortlist:
        record = history.get(slug)
        if record is None:
            continue
        rec_date = _parse_record_date(record.last_updated)
        if rec_date is not None and (latest_date is None or rec_date > latest_date):
            latest_date = rec_date
        delta_7d_pct = ((record.effective_price_1m - record.ma_7d) / record.ma_7d) * 100 if record.ma_7d > 0 else 0.0
        prices_shortlist.append(ModelPrice(
            model=slug,
            price_1m=record.effective_price_1m,
            ma_7d=record.ma_7d,
            ma_3d=record.ma_3d,
            change_vs_7d_pct=delta_7d_pct,
            prompt_price_raw=record.advertised_prompt_1m,
            completion_price_raw=record.advertised_completion_1m,
            price=PricePoint(
                advertised_prompt_1m=record.advertised_prompt_1m,
                advertised_completion_1m=record.advertised_completion_1m,
                effective_price_1m=record.effective_price_1m,
            ),
            canonical_slug=(effective_store.get(slug) or {}).get("canonical_slug"),
            source=entry_by_model.get(slug, {}).get("source"),
            is_default=slug == current_default,
        ))
    prices_shortlist.sort(key=lambda p: p.price_1m)

    if latest_date is None or latest_date < today:
        messages.append(DATA_STALE_MESSAGE)

    all_alerts = alerts_store.get("price_warnings", [])
    if target:
        alert_dicts = [w for w in all_alerts
                       if w.get("model") == target or w.get("current_default") == target or w.get("suggested_cheapest") == target]
    else:
        alert_dicts = all_alerts

    return TrackerResult(
        status="success",
        timestamp=now.isoformat(),
        # Always a local-storage read, never a live call -- see D-19: `check`
        # never attempts the OpenRouter API, so its data is definitionally
        # "cached_history", not a fresh "live_api" observation.
        fallback=True,
        prices_shortlist=prices_shortlist,
        price_warnings=[_price_warning_from_dict(w) for w in alert_dicts],
        storage_path=str(hist_path),
        config_path=str(cfg_path),
        hermes_integration=hermes_status,
        analytics_mode=False,
        hints_enabled=hints_enabled,
        messages=messages,
    )


def read_history_result(
    config_path: Path | None = None,
    history_path: Path | None = None,
    hermes_config_path: str | Path | None = None,
    no_hermes: bool = False,
    hints_enabled: bool = False,
    model_id: str | None = None,
) -> TrackerResult:
    """Local-only 30-day analytics read (D-19 `history`/`get_model_history`):
    owns all analytics/profile classification. Source is history.csv's
    already-derived d1..d30/MA columns (in turn derived from
    effective_prices.json by the last `run`, §5.2). Makes no OpenRouter
    network call."""
    cfg_path = config_path or get_config_path()
    hist_path = history_path or get_history_path()
    cfg = load_config(cfg_path)

    target = model_id.strip() if model_id else None
    if target is not None and target not in cfg.get("shortlist", []):
        return _local_not_monitored_result(target, cfg_path, hist_path)

    cfg, hermes_status, messages = _local_hermes_snapshot(cfg_path, cfg, hermes_config_path, no_hermes)
    entries = cfg.get("_shortlist_entries", [])
    shortlist = cfg.get("shortlist", [])
    history = read_history(hist_path)
    effective_store = read_effective_prices(get_effective_prices_path(hist_path.parent))
    configured_default = default_model(entries)
    if configured_default is None:
        messages.append(AgentMessage("info", "NO_DEFAULT", "No default model is set; default-based alerts are off."))

    today = datetime.now(timezone.utc).date()
    candidates = {slug: record.effective_price_1m for slug, record in history.items() if slug in shortlist}
    prices: list[ModelPrice] = []
    latest_date: date | None = None
    for slug in ([target] if target else shortlist):
        record = history.get(slug)
        if record is None:
            continue
        rec_date = _parse_record_date(record.last_updated)
        if rec_date is not None and (latest_date is None or rec_date > latest_date):
            latest_date = rec_date
        analytics = calculate_model_analytics(
            model_id=slug,
            current_price=record.effective_price_1m,
            history_prices=record.prices,
            candidate_prices=candidates,
            current_default=configured_default,
            min_tracking_days_for_profile=cfg.get("min_tracking_days_for_profile", 14),
            tracking_days_elapsed=tracking_days_elapsed(effective_store, slug, today),
        )
        entry = next((item for item in entries if item["model"] == slug), {})
        prices.append(ModelPrice(
            model=slug,
            price_1m=record.effective_price_1m,
            ma_7d=record.ma_7d,
            ma_3d=record.ma_3d,
            change_vs_7d_pct=((record.effective_price_1m - record.ma_7d) / record.ma_7d * 100) if record.ma_7d else 0.0,
            analytics=analytics,
            canonical_slug=(effective_store.get(slug) or {}).get("canonical_slug"),
            source=entry.get("source"),
            is_default=slug == configured_default,
        ))
    prices.sort(key=lambda p: p.price_1m)

    if latest_date is None or latest_date < today:
        messages.append(DATA_STALE_MESSAGE)

    return TrackerResult(
        status="success",
        timestamp=datetime.now(timezone.utc).isoformat(),
        fallback=True,
        prices_shortlist=prices,
        price_warnings=[],
        storage_path=str(hist_path),
        config_path=str(cfg_path),
        hermes_integration=hermes_status,
        analytics_mode=True,
        hints_enabled=hints_enabled,
        messages=messages,
    )
