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
from typing import Any, Dict, List, Optional

import requests

from anticharon.analytics import calculate_model_analytics
from anticharon.config import get_config_path, get_history_path, load_config
from anticharon.hermes import get_hermes_models, sync_hermes_to_config
from anticharon.models import (
    HermesIntegrationStatus,
    ModelPrice,
    PricePoint,
    PriceWarning,
    TrackerResult,
)
from anticharon.pricing import (
    blended_rate_1m,
    is_valid_listed_price,
    parse_required_price_1m,
    resolve_cache_read_price_1m,
)
from anticharon.storage import (
    derive_history_window,
    get_effective_prices_path,
    is_model_backfill_stale,
    read_effective_prices,
    read_history,
    write_effective_prices,
    write_history,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
# Internal, unauthenticated frontend routes -- no formal SLA, same graceful-degradation
# contract as every other network call in this codebase (see PLAN.md "Policy (ZDR)
# pricing data source" and "28-Day Backfill").
OPENROUTER_ENDPOINT_STATS_URL = "https://openrouter.ai/api/frontend/v1/stats/endpoint"
OPENROUTER_EFFECTIVE_PRICING_URL = "https://openrouter.ai/api/frontend/v1/stats/effective-pricing"


def fetch_openrouter_models(timeout: float = 10.0) -> Dict[str, Any]:
    """Fetch all active model records from OpenRouter public bulk catalog (advertised price/metadata)."""
    try:
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=timeout)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return {m["id"]: m for m in data if "id" in m}
    except Exception as e:
        print(f"[WARN] Failed to query OpenRouter API ({e}). Falling back to cached history.", file=sys.stderr)
        return {}


def fetch_endpoint_policy_pricing(canonical_slug: str, timeout: float = 10.0) -> List[Dict[str, Any]]:
    """Per-endpoint effective/policy pricing + the real, unauthenticated ZDR signal
    (`provider_info.dataPolicy.retainsPrompts`) -- supersedes the public
    `/models/{slug}/endpoints` call for this project (live-verified: that call's
    `status` field reports 0/routable for everyone on an unauthenticated request).
    Graceful degradation: [] on any failure."""
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
        return resp.json().get("data", [])
    except Exception:
        return []


def extract_endpoint_listed_prices_1m(endpoints: List[Dict[str, Any]]) -> List[float]:
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
    prices: List[float] = []
    for ep in endpoints:
        pricing = ep.get("pricing") or {}
        p_in = parse_required_price_1m(pricing, "prompt")
        if p_in is not None and is_valid_listed_price(p_in):
            prices.append(p_in)
    return prices


def fetch_effective_pricing_history(canonical_slug: str, timeout: float = 10.0) -> Dict[str, Any]:
    """28-day backfill source. `range=1m` is required for ~30 days of daily
    observations -- live-verified: the bare/default call (no `range`) only
    returns the last 8 days. Graceful degradation: {} on failure, or when the
    model has no persistent history of its own (e.g. a `~`-prefixed router
    alias like `~deepseek/deepseek-pro-latest`, live-verified to return an
    empty-but-200-OK payload since "latest" has no fixed permaslug identity)."""
    try:
        resp = requests.get(
            OPENROUTER_EFFECTIVE_PRICING_URL,
            params={"permaslug": canonical_slug, "shape": "v7", "variant": "standard", "range": "1m"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("data", {})
    except Exception:
        return {}


def _endpoint_blended_rate_1m(
    endpoint: Dict[str, Any], w_uncached: float, w_cached: float, w_completion: float
) -> Optional[float]:
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
    endpoints: List[Dict[str, Any]],
    w_uncached: float,
    w_cached: float,
    w_completion: float,
    zdr_only: bool,
) -> Dict[str, Any]:
    """effective_price_1m = cheapest endpoint's blended rate (always, when endpoint
    data is available). policy_price_1m/is_policy_routable/excluded_providers are
    only populated when `zdr_only` is active -- an inactive policy filter means
    there's no policy price at all (see PLAN.md "Core pricing semantics")."""
    rates: List[float] = []
    zdr_rates: List[float] = []
    excluded_providers: List[str] = []

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

    result: Dict[str, Any] = {
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


def _reduce_to_daily_observations(history_data: Dict[str, Any], w_completion: float) -> List[Dict[str, Any]]:
    """Collapse the effective-pricing route's per-endpoint daily input/output series
    into one blended $/1M observation per calendar day (the cheapest endpoint that
    day). OpenRouter's per-endpoint series is already cache-weighted by that
    provider's real traffic that day -- only the input/output combination is ours
    to apply, via the locally calibrated `weight_completion` split."""
    input_series = history_data.get("inputChartData") or []
    output_series = history_data.get("outputChartData") or []
    output_by_date: Dict[str, Dict[str, float]] = {
        entry.get("x", "").split(" ")[0]: (entry.get("y") or {}) for entry in output_series
    }

    observations: List[Dict[str, Any]] = []
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
    store: Dict[str, Any],
    w_completion: float,
    timeout: float,
    now: Optional[datetime] = None,
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


def tracking_days_elapsed(store: Dict[str, Any], model_id: str, today: date) -> Optional[int]:
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


def run_tracker(
    dry_run: bool = False,
    config_path: Optional[Path] = None,
    history_path: Optional[Path] = None,
    timeout: float = 10.0,
    hermes_config_path: Optional[str | Path] = None,
    no_hermes: bool = False,
    enable_analytics: bool = False,
    hints_enabled: bool = False,
    zdr_only: bool = False,
) -> TrackerResult:
    """Execute price tracker workflow."""
    cfg_path = config_path or get_config_path()
    cfg = load_config(cfg_path)
    hist_path = history_path or get_history_path()
    history = read_history(hist_path)
    effective_prices_path = get_effective_prices_path(hist_path.parent)
    effective_store = read_effective_prices(effective_prices_path)

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

    w_uncached = cfg.get("weight_uncached_prompt", 0.232622)
    w_cached = cfg.get("weight_cached_prompt", 0.764478)
    w_completion = cfg.get("weight_completion", 0.0029)
    threshold = cfg.get("spike_threshold_pct", 20.0)
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    today = now.date()

    # Fallback mode when API query returns empty
    if not models_api and history:
        prices_shortlist = []
        for model_id in shortlist:
            if model_id in history:
                rec = history[model_id]
                delta_7d_pct = ((rec.effective_price_1m - rec.ma_7d) / rec.ma_7d) * 100 if rec.ma_7d > 0 else 0.0
                prices_shortlist.append(ModelPrice(
                    model=model_id,
                    price_1m=rec.effective_price_1m,
                    ma_7d=rec.ma_7d,
                    ma_3d=rec.ma_3d,
                    change_vs_7d_pct=delta_7d_pct,
                    price=PricePoint(
                        advertised_prompt_1m=rec.advertised_prompt_1m,
                        advertised_completion_1m=rec.advertised_completion_1m,
                        effective_price_1m=rec.effective_price_1m,
                        cache_hit_rate_used=w_cached,
                    ),
                ))
        prices_shortlist.sort(key=lambda x: x.price_1m)
        if enable_analytics:
            cand = {p.model: p.price_1m for p in prices_shortlist}
            c_def = shortlist[0] if shortlist else None
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

        # PE2-002: prompt/completion are required bulk-catalog fields -- a
        # missing/blank/malformed value must skip the model entirely, never
        # fabricate a $0 advertised price (live-verified 2026-09-17: every
        # real catalog entry, including :free models, always includes both
        # keys explicitly; see parse_required_price_1m).
        pricing = api_data.get("pricing", {})
        advertised_prompt_1m = parse_required_price_1m(pricing, "prompt")
        advertised_completion_1m = parse_required_price_1m(pricing, "completion")
        if advertised_prompt_1m is None or advertised_completion_1m is None:
            continue

        if not (is_valid_listed_price(advertised_prompt_1m) and is_valid_listed_price(advertised_completion_1m)):
            # Sentinel/non-priced model (e.g. a meta-router like openrouter/auto-beta) --
            # skip rather than let a negative sentinel masquerade as "cheapest".
            continue

        canonical_slug = api_data.get("canonical_slug") or model_id

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
                model=model_id,
                policy="zdr",
                excluded_providers=policy_result["excluded_providers"],
                reason="No ZDR-compliant endpoint (dataPolicy.retainsPrompts=false) is currently routable.",
                message=f"Model {model_id} has no ZDR-compliant endpoint; policy price unavailable."
            ))
        elif zdr_only and is_policy_routable is None:
            # PE2-003: policy-unknown (the internal per-endpoint route failed, returned
            # no usable pricing, or genuinely reported zero endpoints) must be surfaced
            # explicitly, not silently conflated with confirmed noncompliance -- and per
            # PLAN.md's graceful-degradation rule, treated as routable-by-default for
            # ranking (see _rank_price_1m below), not excluded.
            warnings.append(PriceWarning(
                type="POLICY_UNKNOWN",
                model=model_id,
                policy="zdr",
                reason="ZDR compliance could not be determined (endpoint data unavailable); "
                       "falling back to the unconstrained effective price for ranking.",
                message=f"Model {model_id}'s ZDR compliance is unknown; treating as routable by default."
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
            model_id, canonical_slug, effective_store, w_completion, timeout, now=now
        )
        observations = (effective_store.get(model_id) or {}).get("observations", [])
        derived = derive_history_window(observations, today=today)
        ma_3d = derived["ma_3d"] if derived["ma_3d"] is not None else effective_price_1m
        ma_7d = derived["ma_7d"] if derived["ma_7d"] is not None else effective_price_1m
        slots = derived["slots"]

        delta_7d_pct = ((effective_price_1m - ma_7d) / ma_7d) * 100 if ma_7d > 0 else 0.0

        # Anomaly / Spikes / Drops detection
        if delta_7d_pct >= threshold:
            warnings.append(PriceWarning(
                type="PRICE_SPIKE",
                model=model_id,
                message=f"Model {model_id} price spiked +{delta_7d_pct:.1f}% vs 7-day MA. Current: ${effective_price_1m:.5f}/1M."
            ))
        elif delta_7d_pct <= -threshold:
            warnings.append(PriceWarning(
                type="PRICE_DROP",
                model=model_id,
                message=f"Model {model_id} price dropped {abs(delta_7d_pct):.1f}% vs 7-day MA. Current: ${effective_price_1m:.5f}/1M."
            ))

        prices_shortlist.append(ModelPrice(
            model=model_id,
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
                cache_hit_rate_used=w_cached,
            ),
        ))

        updated_records.append([
            model_id, now_iso, effective_price_1m, advertised_prompt_1m, advertised_completion_1m,
            ma_3d, ma_7d,
            slots["d1"], slots["d2"], slots["d3"], slots["d4"], slots["d5"], slots["d6"], slots["d7"],
            slots["d15"], slots["d30"],
        ])

    # Persist records unless dry_run
    if not dry_run and updated_records:
        write_history(updated_records, hist_path)
        write_effective_prices(effective_store, effective_prices_path)

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

    # Check if lowest-cost option differs from default (first in shortlist)
    if shortlist:
        current_default = shortlist[0]
        if prices_shortlist and prices_shortlist[0].model != current_default:
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
        c_def = shortlist[0] if shortlist else None
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
        hints_enabled=hints_enabled
    )
