"""Command-line interface (CLI) for Anticharon."""

import argparse
import csv
import json
import sys
import time
from pathlib import Path

from anticharon import __version__
from anticharon.chart import render_ascii_price_bar
from anticharon.config import (
    get_config_path,
    get_history_path,
    load_config,
    update_config_weights,
)
from anticharon.discovery import (
    apply_zdr_filter,
    fetch_catalog,
    filter_catalog,
    format_discovery_output,
)
from anticharon.hermes import (
    build_hermes_import_payload,
    get_hermes_models,
    shortlist_write_message,
)
from anticharon.log_parser import parse_activity_log
from anticharon.manager import add_model, list_models, remove_model
from anticharon.models import (
    ERROR_STATUSES,
    AgentMessage,
    TrackerResult,
    build_envelope,
    render_messages,
)
from anticharon.tester import run_self_test
from anticharon.tracker import run_tracker


def _exit_code(status: str) -> int:
    """CLI exit code for an envelope status: 1 iff the operation was not performed (A2A-3)."""
    return 1 if status in ERROR_STATUSES else 0


def _print_hermes_line(result: TrackerResult) -> None:
    """Hermes detection line; whether anything was persisted is stated by messages (A2A-7)."""
    h = result.hermes_integration
    if h and h.detected:
        print(f"🤖 Hermes:    Detected ({h.models_count} models via {h.method} from {h.source})")
    elif h and h.method == "standalone":
        print("🤖 Hermes:    Standalone mode (Anticharon shortlist.json)")


def format_human_output(result: TrackerResult, messages: list[dict]) -> None:
    """Format and print human-readable CLI summary; `messages` are the envelope's."""
    print("\n" + "=" * 74)
    print(f"🪙  ANTICHARON — OpenRouter Price Monitor (v{__version__})")
    print(f"📅 Timestamp: {result.timestamp}")
    if result.storage_path:
        print(f"💾 Storage:   {result.storage_path}")
    if result.config_path:
        print(f"⚙️  Config:    {result.config_path}")
    _print_hermes_line(result)
    if result.fallback:
        print("⚠️  [STATUS: OFFLINE FALLBACK] Using cached history prices.")
    else:
        print("🟢 [STATUS: LIVE API] Latest OpenRouter prices fetched.")
    print("=" * 74)

    default_model = next((p.model for p in result.prices_shortlist if p.is_default), None)

    print(f"{'MODEL':<34} {'EFFECTIVE/1M':<13} {'MA 7D':<12} {'CHANGE (7D)':<10}")
    print("-" * 74)

    for idx, p in enumerate(result.prices_shortlist):
        change_str = f"{p.change_vs_7d_pct:+.1f}%" if p.change_vs_7d_pct != 0 else "0.0%"
        badges = []
        if idx == 0:
            badges.append("🏆 [BEST]")
        if default_model and p.model == default_model:
            badges.append("★ [DEFAULT]")
        badge_str = f" {' '.join(badges)}" if badges else ""
        print(f"{p.model:<34} ${p.price_1m:<12.5f} ${p.ma_7d:<11.5f} {change_str:<10}{badge_str}")
        if p.price:
            # Advertised is a raw (never blended) prompt/completion pair -- a
            # transparency anchor only, distinct from the effective blend above.
            detail = f"    ↳ advertised: ${p.price.advertised_prompt_1m:.4f} in / ${p.price.advertised_completion_1m:.4f} out /1M"
            if p.price.policy_price_1m is not None:
                detail += f"  |  policy (ZDR): ${p.price.policy_price_1m:.5f}/1M"
            elif p.price.is_policy_routable is False:
                detail += "  |  policy (ZDR): unroutable"
            print(detail)

    print("-" * 74)

    # TUI ASCII Price Spectrum Chart
    if result.prices_shortlist:
        chart_lines = render_ascii_price_bar(result.prices_shortlist, default_model=default_model)
        print("\n" + "\n".join(chart_lines))
        print("-" * 74)

    if result.price_warnings:
        print("\n🚨 ALERTS & WARNINGS:")
        for w in result.price_warnings:
            if w.type == "PRICE_SPIKE":
                print(f"  🔴 [SPIKE] {w.message}")
            elif w.type == "PRICE_DROP":
                print(f"  🟢 [DROP]  {w.message}")
            elif w.type == "BEST_OPTION_CHANGED":
                print(f"  💡 [TIP]   {w.message}")
            elif w.type == "POLICY_UNROUTABLE":
                print(f"  🚫 [POLICY] {w.message}")
            elif w.type == "POLICY_UNKNOWN":
                print(f"  ❓ [POLICY] {w.message}")
    else:
        print("\n✅ All monitored models are within normal price fluctuation boundaries.")
    print("-" * 74)
    render_messages(messages)
    print("=" * 74 + "\n")


def format_analytics_human_output(result: TrackerResult, messages: list[dict]) -> None:
    """Format TrackerResult with deep 30-day analytical intelligence and profiles."""
    print("\n" + "=" * 104)
    print(f"🪙  ANTICHARON — Analytical Price Intelligence & History (v{__version__})")
    print(f"📅 Timestamp: {result.timestamp}")
    if result.storage_path:
        print(f"💾 Storage:   {result.storage_path}")
    if result.config_path:
        print(f"⚙️  Config:    {result.config_path}")

    _print_hermes_line(result)

    status_str = "CACHED HISTORY (Offline Fallback)" if result.fallback else "LIVE API"
    status_icon = "🟠" if result.fallback else "🟢"
    print(f"{status_icon} [STATUS: {status_str}]")
    print("=" * 104)

    default_model = next((p.model for p in result.prices_shortlist if p.is_default), None)

    print(f"{'MODEL':<33} {'PRICE/1M':<10} {'30D TREND':<18} {'PROFILE':<17} {'RECOMMENDATION'}")
    print("-" * 104)

    stable_models = []
    promo_ended_models = []
    sunsetting_models = []
    discounted_models = []
    volatile_models = []

    for p in result.prices_shortlist:
        an = p.analytics
        badge = an.badge if an else "—"
        spark = an.trajectory_sparkline if an else "—"
        rec = an.recommendation if an else ""

        if an:
            if an.profile == "STABLE":
                stable_models.append((p.model, p.price_1m, an.volatility_cv_pct))
            elif an.profile == "PROMO_ENDED":
                promo_ended_models.append((p.model, an.change_vs_30d_pct, an.volatility_cv_pct))
            elif an.profile == "SUNSETTING":
                sunsetting_models.append((p.model, an.recommendation))
            elif an.profile == "DISCOUNTED":
                discounted_models.append((p.model, an.change_vs_30d_pct))
            elif an.profile == "VOLATILE":
                volatile_models.append((p.model, an.volatility_cv_pct))

        def_badge = " ★[DEF]" if default_model and p.model == default_model else ""
        model_display = f"{p.model}{def_badge}"
        print(f"{model_display:<33} ${p.price_1m:<9.5f} {spark:<18} {badge:<17} {rec}")
        if an and an.secondary_badge:
            print(f"{'':<33} {'':<10} {'':<18} {an.secondary_badge:<17}")

    print("-" * 104)

    # Summary Insights
    print("\n📊 30-DAY VOLATILITY & SPREAD SUMMARY:")
    if stable_models:
        st_desc = ", ".join([f"{m.split('/')[-1]} (${pr:.3f})" for m, pr, _ in stable_models[:4]])
        print(f"  • STABLE WORKHORSES: {st_desc} [CV < 2.5%]")
    if promo_ended_models:
        for m, delta, cv in promo_ended_models:
            print(f"  • EXPIRED PROMO: {m} rose {delta:+.1f}% over baseline (CV: {cv:.1f}%).")
    if sunsetting_models:
        for m, rec in sunsetting_models:
            print(f"  • MIGRATION OPPORTUNITY: {m} — {rec}")
    if discounted_models:
        for m, delta in discounted_models:
            print(f"  • ACTIVE DISCOUNT: {m} is discounted {delta:.1f}% vs 30d baseline.")
    if volatile_models:
        for m, cv in volatile_models:
            print(f"  • HIGH VOLATILITY: {m} shows erratic price changes (CV: {cv:.1f}%).")

    if result.price_warnings:
        print("\n🚨 ALERTS & WARNINGS:")
        for w in result.price_warnings:
            if w.type == "PRICE_SPIKE":
                print(f"  🔴 [SPIKE] {w.message}")
            elif w.type == "PRICE_DROP":
                print(f"  🟢 [DROP]  {w.message}")
            elif w.type == "BEST_OPTION_CHANGED":
                print(f"  💡 [TIP]   {w.message}")
            elif w.type == "POLICY_UNROUTABLE":
                print(f"  🚫 [POLICY] {w.message}")
            elif w.type == "POLICY_UNKNOWN":
                print(f"  ❓ [POLICY] {w.message}")

    print("-" * 104)
    render_messages(messages)
    print("=" * 104 + "\n")


def _emit_tracker_result(res: TrackerResult, started: float, as_json: bool, is_analytics: bool) -> int:
    """Print a tracker result as the JSON envelope or human report; return the exit code."""
    envelope = build_envelope(res.to_dict(), res.messages, started)
    if as_json:
        print(json.dumps(envelope, indent=2))
    elif is_analytics:
        format_analytics_human_output(res, envelope["messages"])
    else:
        format_human_output(res, envelope["messages"])
    return _exit_code(envelope["status"])


def cmd_run(args) -> int:
    """Handle `run` and `check` commands."""
    started = time.perf_counter()
    hist_path = Path(args.data_dir) / "history.csv" if getattr(args, "data_dir", None) else get_history_path()
    if getattr(args, "history_csv", False):
        if not hist_path.exists():
            print(f"History file not found at {hist_path}", file=sys.stderr)
            return 1
        print(hist_path.read_text(encoding="utf-8").strip())
        return 0

    is_analytics = getattr(args, "profile", False) or getattr(args, "analytics", False)
    res = run_tracker(
        dry_run=args.dry_run,
        config_path=Path(args.config) if args.config else None,
        history_path=hist_path,
        timeout=args.timeout,
        hermes_config_path=getattr(args, "hermes_config", None),
        no_hermes=getattr(args, "no_hermes", False),
        enable_analytics=is_analytics,
        hints_enabled=getattr(args, "hints", False),
        zdr_only=getattr(args, "zdr", False),
        model_id=getattr(args, "model_id", None),
    )
    return _emit_tracker_result(res, started, args.json, is_analytics)


def cmd_history(args) -> int:
    """Handle `history` analytical command."""
    started = time.perf_counter()
    hist_path = Path(args.data_dir) / "history.csv" if getattr(args, "data_dir", None) else get_history_path()
    if getattr(args, "csv", False) or getattr(args, "history_csv", False):
        if not hist_path.exists():
            print(f"History file not found at {hist_path}", file=sys.stderr)
            return 1
        print(hist_path.read_text(encoding="utf-8").strip())
        return 0

    res = run_tracker(
        dry_run=True,
        config_path=Path(args.config) if getattr(args, "config", None) else None,
        history_path=hist_path,
        timeout=getattr(args, "timeout", 10.0),
        hermes_config_path=getattr(args, "hermes_config", None),
        no_hermes=getattr(args, "no_hermes", False),
        enable_analytics=True,
        hints_enabled=getattr(args, "hints", False)
    )
    return _emit_tracker_result(res, started, getattr(args, "json", False), True)


def cmd_info(args) -> int:
    """Handle `info` command to output llms.txt A2A discovery briefing."""
    started = time.perf_counter()
    content = None

    # Tier 1: Try package resource (works when installed via uv tool / pip)
    try:
        import importlib.resources as pkg_resources
        content = pkg_resources.files("anticharon").joinpath("llms.txt").read_text(encoding="utf-8").strip()
    except Exception:
        content = None

    # Tier 2: Search filesystem candidates (git root, home directory, dotfolder)
    if not content:
        llms_candidates = [
            Path(__file__).resolve().parent / "llms.txt",
            Path(__file__).resolve().parent.parent.parent / "llms.txt",
            Path.cwd() / "llms.txt",
            Path.home() / "anticharon" / "llms.txt",
            Path.home() / ".anticharon" / "llms.txt"
        ]
        for cand in llms_candidates:
            if cand.exists():
                try:
                    text = cand.read_text(encoding="utf-8").strip()
                    if text:
                        content = text
                        break
                except Exception:
                    continue

    if not content:
        content = (
            "# Anticharon Price Optimizer\n"
            "OpenRouter model price tracker and token cost optimizer.\n"
            "Run `anticharon check --json` to inspect prices and alerts."
        )

    # Auto-seed ~/.anticharon/llms.txt for local agent discovery
    try:
        user_dot = Path.home() / ".anticharon" / "llms.txt"
        if not user_dot.exists() and content:
            user_dot.parent.mkdir(parents=True, exist_ok=True)
            user_dot.write_text(content, encoding="utf-8")
    except Exception:
        pass

    if getattr(args, "json", False):
        print(json.dumps(build_envelope({"status": "success", "content": content}, [], started), indent=2))
    else:
        print(content)
    return 0


def cmd_mcp(args) -> int:
    """Handle `mcp` server execution command over stdio."""
    from anticharon.mcp import run_mcp_server
    transport = getattr(args, "transport", "stdio")
    run_mcp_server(transport=transport)
    return 0


def cmd_test(args) -> int:
    """Handle `test` diagnostic command."""
    success = run_self_test(
        hermes_config_path=getattr(args, "hermes_config", None),
        no_hermes=getattr(args, "no_hermes", False),
        json_mode=getattr(args, "json", False)
    )
    return 0 if success else 1


def cmd_calibrate(args) -> int:
    """Handle `calibrate` log ingestion command."""
    started = time.perf_counter()
    as_json = getattr(args, "json", False)
    try:
        mix = parse_activity_log(args.csv_file)
    except (OSError, UnicodeError, ValueError, csv.Error) as e:
        # Only invalid/unreadable input maps to CALIBRATION_INPUT_INVALID (D-1e);
        # any other exception is an internal failure and is not reported as bad input.
        envelope = build_envelope({"status": "error", "csv_file": Path(args.csv_file).name}, [AgentMessage(
            "error", "CALIBRATION_INPUT_INVALID",
            f"Could not read activity log '{Path(args.csv_file).name}' ({type(e).__name__}); "
            f"weights were not changed.",
            action={"cli": "export the CSV from https://openrouter.ai/logs (⋯ → Export) and run anticharon calibrate <csv>"},
        )], started)
        if as_json:
            print(json.dumps(envelope, indent=2))
        else:
            render_messages(envelope["messages"], file=sys.stderr)
        return _exit_code(envelope["status"])

    is_dry_run = getattr(args, "dry_run", False)
    cfg_path = Path(args.config) if args.config else get_config_path()
    if not is_dry_run:
        cfg_path = update_config_weights(
            mix.weight_uncached_prompt, mix.weight_cached_prompt, mix.weight_completion, cfg_path
        )
    envelope = build_envelope(
        {"status": "success", **mix.to_dict(), "dry_run": is_dry_run, "config_path": str(cfg_path)},
        [shortlist_write_message(True, is_dry_run, "calibrated token weights")],
        started,
    )

    if as_json:
        print(json.dumps(envelope, indent=2))
        return _exit_code(envelope["status"])

    print("\n" + "=" * 60)
    print("📊 OpenRouter Token Mix & Calibration Analysis")
    print("=" * 60)
    print(f" Records processed:       {mix.records_count:,}")
    print(f" Total Prompt Tokens:     {mix.total_prompt_tokens:,}")
    print(f"   Uncached: {mix.total_uncached_tokens:,} ({mix.weight_uncached_prompt*100:.2f}%)")
    print(f"   Cached:   {mix.total_cached_tokens:,} ({mix.weight_cached_prompt*100:.2f}%, cache-hit-rate {mix.cache_hit_rate*100:.2f}%)")
    print(f" Total Completion Tokens: {mix.total_completion_tokens:,} ({mix.weight_completion*100:.2f}%)")
    print(f" Total Tokens:            {mix.total_tokens:,}")
    print("-" * 60)
    print(f" Calculated Weight Uncached Prompt: {mix.weight_uncached_prompt:.6f}")
    print(f" Calculated Weight Cached Prompt:    {mix.weight_cached_prompt:.6f}")
    print(f" Calculated Weight Completion:       {mix.weight_completion:.6f}")
    print("-" * 60)
    print(" 💡 TraceLab Real-World Context (UW TraceLab Dataset):")
    print("    Claude Code / Codex traces report 99.63% in / 0.37% out.")
    print("    Accurate blended weighting reduces token cost anxiety")
    print("    and empowers running premium models responsibly.")
    print("=" * 60)
    print(f"⚙️ Config: {cfg_path}")
    render_messages(envelope["messages"])
    print()
    return _exit_code(envelope["status"])


def _print_management_result(res, envelope: dict) -> None:
    """Human output for `model add` / `remove`: messages, then the resulting shortlist."""
    print()
    render_messages(envelope["messages"])
    print(f"📋 Current Shortlist ({len(res.shortlist)} models):")
    for m in res.shortlist:
        print(f"  • {m}")
    print(f"⚙️ Config: {res.config_path}\n")


def cmd_model(args) -> int:
    """Handle `model` subcommands (add, remove, list, discover)."""
    started = time.perf_counter()
    action = getattr(args, "model_action", None)
    cfg_path = Path(args.config) if getattr(args, "config", None) else None
    as_json = getattr(args, "json", False)

    if action in ("add", "remove", "list"):
        if action == "add":
            res = add_model(
                model_id=args.model_id,
                dry_run=args.dry_run,
                config_path=cfg_path,
                default=getattr(args, "default", False),
            )
        elif action == "remove":
            res = remove_model(model_id=args.model_id, dry_run=args.dry_run, config_path=cfg_path)
        else:
            res = list_models(config_path=cfg_path)
        envelope = build_envelope(res.to_dict(), res.messages, started)
        if as_json:
            print(json.dumps(envelope, indent=2))
        elif action == "list":
            print(f"\n📋 Shortlisted Models ({len(res.shortlist)}):")
            print(f"⚙️ Config: {res.config_path}")
            print("-" * 50)
            defaults = {entry["model"] for entry in res.entries if entry.get("order") == 0}
            for idx, m in enumerate(res.shortlist, 1):
                entry = next((e for e in res.entries if e["model"] == m), {"source": "manual"})
                badge = " (Default Model)" if m in defaults else ""
                print(f" {idx}. {m} [{entry.get('source', 'manual')}]{badge}")
            print("-" * 50)
            render_messages(envelope["messages"])
            print()
        else:
            _print_management_result(res, envelope)
        return _exit_code(envelope["status"])

    elif action == "discover":
        cfg = load_config(cfg_path)
        w_uncached = cfg.get("weight_uncached_prompt", 0.232622)
        w_cached = cfg.get("weight_cached_prompt", 0.764478)
        w_completion = cfg.get("weight_completion", 0.0029)

        catalog = fetch_catalog(
            weight_uncached_prompt=w_uncached,
            weight_cached_prompt=w_cached,
            weight_completion=w_completion,
        )
        filtered = filter_catalog(
            models=catalog,
            query=args.query,
            promo_only=args.promo,
            modality=args.modality,
            max_price=args.max_price,
            max_input_price=args.max_input_price,
            max_output_price=args.max_output_price,
            filter_expressions=args.filter
        )

        messages: list[AgentMessage] = []
        if getattr(args, "zdr", False):
            # Live ZDR check runs only against the already-narrowed local-filter
            # result, not the full catalog -- and is itself capped (see apply_zdr_filter).
            max_zdr_check_count = cfg.get("max_zdr_check_count", 10)
            filtered, zdr_limit = apply_zdr_filter(filtered, max_check_count=max_zdr_check_count)
            if zdr_limit:
                messages.append(AgentMessage("warning", "ZDR_LIVE_LIMITED", f"Live ZDR results are limited: {zdr_limit}"))

        format_discovery_output(filtered, json_mode=as_json, messages=messages, started=started)
        return 0

    elif action in ("sync", "import-hermes"):
        hermes_custom = getattr(args, "hermes_config", None)
        hermes_info = get_hermes_models(custom_path=hermes_custom, prompt_if_missing=True)
        is_dry_run = getattr(args, "dry_run", False)
        payload, messages = build_hermes_import_payload(hermes_info, config_path=cfg_path, dry_run=is_dry_run)
        envelope = build_envelope(payload, messages, started)
        if as_json:
            print(json.dumps(envelope, indent=2))
            return _exit_code(envelope["status"])

        if payload["detected"]:
            prefix = "[DRY RUN] Would import" if is_dry_run else "Imported"
            print(f"\n✅ {prefix} {len(payload['shortlist'])} models from Hermes ({payload['source']})")
            print("🔒 Hermes configuration is untouched (read-only).")
            print(f"★ Default Model: {payload['default_model']}")
            print("📋 Shortlist:")
            for idx, m in enumerate(payload["shortlist"], 1):
                badge = " ★ [DEFAULT]" if idx == 1 else ""
                print(f"  {idx}. {m}{badge}")
            print(f"⚙️ Anticharon Config: {payload['config_path']}")
        render_messages(envelope["messages"])
        print()
        return _exit_code(envelope["status"])

    return 0


def cmd_help(
    parser: argparse.ArgumentParser,
    subparsers: argparse._SubParsersAction,
    model_subparsers: argparse._SubParsersAction,
    args: argparse.Namespace
) -> int:
    """Display general or subcommand-specific help."""
    target = args.target if isinstance(args.target, list) else ([args.target] if args.target else [])
    if not target:
        parser.print_help()
        return 0

    primary = target[0]
    if primary in subparsers.choices:
        sub = subparsers.choices[primary]
        if len(target) > 1 and primary == "model" and target[1] in model_subparsers.choices:
            model_subparsers.choices[target[1]].print_help()
            return 0
        sub.print_help()
        return 0

    print(
        f"anticharon: error: unknown help target '{primary}'. Run 'anticharon help' for available commands.",
        file=sys.stderr
    )
    return 2


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="anticharon",
        description="Anticharon — The ferryman who minimizes the fare instead of demanding toll."
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--test", action="store_true", help="Run self-test diagnostic suite")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--hints", action="store_true", help="Include self-describing key hints in JSON output")
    parser.add_argument("--profile", action="store_true", help="Display analytical model profiles and 30-day trajectory")
    parser.add_argument("--analytics", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--history-csv", action="store_true", help="Output raw history.csv table to stdout")
    parser.add_argument("--hermes-config", type=str, default=None, help="Path to custom Hermes config.yaml")
    parser.add_argument("--no-hermes", action="store_true", help="Disable Hermes auto-detection and run in standalone mode")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Fetch prices, update history, and display report")
    run_parser.add_argument("--dry-run", action="store_true", help="Do not write updates to history.csv")
    run_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    run_parser.add_argument("--model", dest="model_id", type=str, default=None, help="Update one exact model already in the shortlist")
    run_parser.add_argument("--hints", action="store_true", help="Include self-describing key hints in JSON output")
    run_parser.add_argument("--profile", action="store_true", help="Display analytical model profiles and 30-day trajectory")
    run_parser.add_argument("--analytics", action="store_true", help=argparse.SUPPRESS)
    run_parser.add_argument("--history-csv", action="store_true", help="Output raw history.csv table to stdout")
    run_parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    run_parser.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    run_parser.add_argument("--data-dir", type=str, default=None, help="Directory to store history.csv")
    run_parser.add_argument("--hermes-config", type=str, default=None, help="Path to custom Hermes config.yaml")
    run_parser.add_argument("--no-hermes", action="store_true", help="Disable Hermes auto-detection and run in standalone mode")
    run_parser.add_argument("--zdr", action="store_true", help="Add a policy-constrained price (policy_price_1m) from Zero Data Retention-compliant endpoints; never restricts or replaces effective_price_1m")

    # Command: check (alias for run --dry-run)
    check_parser = subparsers.add_parser("check", help="Check current prices without updating history.csv")
    check_parser.add_argument("--dry-run", action="store_true", default=True, help="Do not write updates to history.csv")
    check_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    check_parser.add_argument("--hints", action="store_true", help="Include self-describing key hints in JSON output")
    check_parser.add_argument("--profile", action="store_true", help="Display analytical model profiles and 30-day trajectory")
    check_parser.add_argument("--analytics", action="store_true", help=argparse.SUPPRESS)
    check_parser.add_argument("--history-csv", action="store_true", help="Output raw history.csv table to stdout")
    check_parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    check_parser.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    check_parser.add_argument("--data-dir", type=str, default=None, help="Directory to store history.csv")
    check_parser.add_argument("--hermes-config", type=str, default=None, help="Path to custom Hermes config.yaml")
    check_parser.add_argument("--no-hermes", action="store_true", help="Disable Hermes auto-detection and run in standalone mode")
    check_parser.add_argument("--zdr", action="store_true", help="Add a policy-constrained price (policy_price_1m) from Zero Data Retention-compliant endpoints; never restricts or replaces effective_price_1m")

    # Command: history
    history_parser = subparsers.add_parser("history", help="Audit 30-day historical intelligence and export CSV")
    history_parser.add_argument("--profile", action="store_true", default=True, help="Display analytical model profiles and trajectory")
    history_parser.add_argument("--analytics", action="store_true", help=argparse.SUPPRESS)
    history_parser.add_argument("--csv", action="store_true", help="Output raw history.csv table to stdout")
    history_parser.add_argument("--history-csv", action="store_true", help=argparse.SUPPRESS)
    history_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    history_parser.add_argument("--hints", action="store_true", help="Include self-describing key hints in JSON output")
    history_parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    history_parser.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    history_parser.add_argument("--data-dir", type=str, default=None, help="Directory to store history.csv")
    history_parser.add_argument("--hermes-config", type=str, default=None, help="Path to custom Hermes config.yaml")
    history_parser.add_argument("--no-hermes", action="store_true", help="Disable Hermes auto-detection")

    # Command: info (Agent-to-Agent discovery / llms.txt)
    info_parser = subparsers.add_parser("info", help="Display Agent-to-Agent (A2A) discovery briefing (llms.txt)")
    info_parser.add_argument("--json", action="store_true", help="Output briefing in JSON format")
    info_parser.add_argument("--llm", action="store_true", help="Explicit alias for LLM/agent briefing")

    # Command: mcp (Model Context Protocol server)
    mcp_parser = subparsers.add_parser("mcp", help="Run Model Context Protocol (MCP) server over stdio")
    mcp_parser.add_argument("--transport", type=str, default="stdio", choices=["stdio", "sse", "streamable-http"], help="MCP transport protocol (default: stdio)")

    # Command: test
    test_parser = subparsers.add_parser("test", help="Run pre-flight self-test and connectivity diagnostics")
    test_parser.add_argument("--json", action="store_true", help="Output diagnostic summary in JSON format")
    test_parser.add_argument("--hermes-config", type=str, default=None, help="Path to custom Hermes config.yaml")
    test_parser.add_argument("--no-hermes", action="store_true", help="Disable Hermes auto-detection during self-test")

    # Command: calibrate
    calib_parser = subparsers.add_parser(
        "calibrate",
        help="Ingest OpenRouter activity CSV and calibrate prompt/completion weights",
        description=(
            "Ingest an exported OpenRouter activity log CSV to calibrate your agent's exact "
            "prompt and completion token weights."
        ),
        epilog=(
            "Technical Rationale (Why local CSV export instead of API polling?):\n"
            "  • Least Privilege & Security: Anticharon deliberately rejects requesting account-wide\n"
            "    management API keys. Ingesting local exports keeps your credentials completely isolated.\n"
            "  • Zero Overhead: OpenRouter lacks an aggregated usage endpoint. Local CSV ingestion\n"
            "    gives instant mathematical clarity without rate-limited sequential network calls.\n\n"
            "How to Export Activity Logs from OpenRouter:\n"
            "  1. Go to OpenRouter Sidebar Logs: https://openrouter.ai/logs\n"
            "  2. Select your desired period on top right (e.g. Past 1 Month)\n"
            "  3. Click the 3 dots menu → Export to download the CSV file.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    calib_parser.add_argument("csv_file", type=str, help="Path to OpenRouter activity log CSV")
    calib_parser.add_argument("--dry-run", action="store_true", help="Calculate and display token mix without modifying configuration")
    calib_parser.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    calib_parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    # Command: model (add, remove, list, discover, sync)
    model_parser = subparsers.add_parser("model", help="Manage shortlisted models and discover OpenRouter catalog")
    model_subparsers = model_parser.add_subparsers(dest="model_action", help="Model actions")

    # model import-hermes (with 'sync' alias)
    sync_p = model_subparsers.add_parser(
        "import-hermes",
        aliases=["sync"],
        help="Import active models from Hermes Agent config into shortlist (read-only on Hermes)"
    )
    sync_p.add_argument("--hermes-config", type=str, default=None, help="Path to custom Hermes config.yaml")
    sync_p.add_argument("--dry-run", action="store_true", help="Preview models without saving to shortlist.json")
    sync_p.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    sync_p.add_argument("--json", action="store_true", help="Output result in JSON format")

    # model add
    add_p = model_subparsers.add_parser("add", help="Add a model to shortlist.json")
    add_p.add_argument("model_id", type=str, help="Model ID (e.g. google/gemini-3.7-flash)")
    add_p.add_argument("--dry-run", action="store_true", help="Preview updated shortlist without saving to disk")
    add_p.add_argument("--default", action="store_true", help="Set this manual model as the default")
    add_p.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    add_p.add_argument("--json", action="store_true", help="Output result in JSON format")

    # model remove
    rm_p = model_subparsers.add_parser("remove", help="Remove a model from shortlist.json")
    rm_p.add_argument("model_id", type=str, help="Model ID to remove")
    rm_p.add_argument("--dry-run", action="store_true", help="Preview updated shortlist without saving to disk")
    rm_p.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    rm_p.add_argument("--json", action="store_true", help="Output result in JSON format")

    # model list
    list_p = model_subparsers.add_parser("list", help="List all shortlisted models")
    list_p.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    list_p.add_argument("--json", action="store_true", help="Output result in JSON format")

    # model discover
    disc_p = model_subparsers.add_parser(
        "discover",
        help="Filter OpenRouter's model catalog by keyword, modality, and price criteria you specify",
        description=(
            "Filters OpenRouter's catalog (~417+ models) by the keyword, modality, and price criteria "
            "you provide, then sorts matches cheapest-first. Plain substring/threshold matching only "
            "-- no AI ranking, curation, or recommendations."
        )
    )
    disc_p.add_argument("query", nargs="?", default=None, help="Optional search query (e.g. 'gemini', 'qwen', 'grok')")
    disc_p.add_argument("--promo", action="store_true", help="Filter for promotional and free (:free, $0.00) models")
    disc_p.add_argument("--modality", type=str, default="text", help="Output modality filter (default: text)")
    disc_p.add_argument("--filter", action="append", default=[], help="Filter keyword or expression (e.g. --filter 'openai' or --filter 'price < 10')")
    disc_p.add_argument("--max-price", type=float, default=None, help="Maximum blended price per 1M tokens ($)")
    disc_p.add_argument("--max-input-price", type=float, default=None, help="Maximum input prompt price per 1M tokens ($)")
    disc_p.add_argument("--max-output-price", type=float, default=None, help="Maximum output completion price per 1M tokens ($)")
    disc_p.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json (for token weights)")
    disc_p.add_argument("--json", action="store_true", help="Output catalog results in JSON format")
    disc_p.add_argument("--zdr", action="store_true", help="Only include models with a Zero Data Retention-compliant endpoint (checked live, after other filters, capped at max_zdr_check_count models -- default 10)")

    # Command: help
    help_parser = subparsers.add_parser(
        "help",
        help="Display general or subcommand help",
        description="Display general help or detailed usage for a specific subcommand."
    )
    help_parser.add_argument("target", nargs="*", help="Subcommand to display help for (e.g. 'run', 'model', 'model discover')")

    args = parser.parse_args()

    if args.command == "help":
        sys.exit(cmd_help(parser, subparsers, model_subparsers, args))

    if args.test or args.command == "test":
        sys.exit(cmd_test(args))

    if args.command in ("run", "check"):
        sys.exit(cmd_run(args))

    if args.command == "history":
        sys.exit(cmd_history(args))

    if args.command == "info":
        sys.exit(cmd_info(args))

    if args.command == "mcp":
        sys.exit(cmd_mcp(args))

    if args.command == "calibrate":
        sys.exit(cmd_calibrate(args))

    if args.command == "model":
        sys.exit(cmd_model(args))

    # Default if no subcommand given: run
    if args.command is None and not args.test:
        hist_path = Path(args.data_dir) / "history.csv" if getattr(args, "data_dir", None) else get_history_path()
        if getattr(args, "history_csv", False):
            if not hist_path.exists():
                print(f"History file not found at {hist_path}", file=sys.stderr)
                sys.exit(1)
            print(hist_path.read_text(encoding="utf-8").strip())
            sys.exit(0)

        started = time.perf_counter()
        is_analytics = getattr(args, "profile", False) or getattr(args, "analytics", False)
        res = run_tracker(
            dry_run=False,
            history_path=hist_path,
            hermes_config_path=getattr(args, "hermes_config", None),
            no_hermes=getattr(args, "no_hermes", False),
            enable_analytics=is_analytics
        )
        sys.exit(_emit_tracker_result(res, started, getattr(args, "json", False), is_analytics))


if __name__ == "__main__":
    main()
