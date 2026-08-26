"""Command-line interface (CLI) for Anticharon."""

import argparse
import json
import sys
from pathlib import Path

from anticharon import __version__
from anticharon.chart import render_ascii_price_bar
from anticharon.config import update_config_weights, get_config_path, load_config
from anticharon.discovery import fetch_catalog, filter_catalog, format_discovery_output
from anticharon.log_parser import parse_activity_log
from anticharon.manager import add_model, remove_model, list_models
from anticharon.tester import run_self_test
from anticharon.tracker import run_tracker


def format_human_output(result) -> None:
    """Format and print human-readable CLI summary."""
    print("\n" + "=" * 74)
    print(f"🪙  ANTICHARON — OpenRouter Price Monitor (v{__version__})")
    print(f"📅 Timestamp: {result.timestamp}")
    if result.storage_path:
        print(f"💾 Storage:   {result.storage_path}")
    if result.config_path:
        print(f"⚙️  Config:    {result.config_path}")
    if result.fallback:
        print("⚠️  [STATUS: OFFLINE FALLBACK] Using cached history prices.")
    else:
        print("🟢 [STATUS: LIVE API] Updated with latest OpenRouter prices.")
    print("=" * 74)

    # Determine default model from config
    default_model = None
    if result.config_path:
        cfg = load_config(Path(result.config_path))
        shortlist = cfg.get("shortlist", [])
        if shortlist:
            default_model = shortlist[0]

    print(f"{'MODEL':<38} {'PRICE/1M':<12} {'MA 7D':<12} {'CHANGE (7D)':<10}")
    print("-" * 74)

    for idx, p in enumerate(result.prices_shortlist):
        change_str = f"{p.change_vs_7d_pct:+.1f}%" if p.change_vs_7d_pct != 0 else "0.0%"
        badges = []
        if idx == 0:
            badges.append("🏆 [BEST]")
        if default_model and p.model == default_model:
            badges.append("★ [DEFAULT]")
        badge_str = f" {' '.join(badges)}" if badges else ""
        print(f"{p.model:<38} ${p.price_1m:<11.5f} ${p.ma_7d:<11.5f} {change_str:<10}{badge_str}")

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
    else:
        print("\n✅ All monitored models are within normal price fluctuation boundaries.")
    print("=" * 74 + "\n")


def cmd_run(args) -> int:
    """Handle `run` and `check` commands."""
    res = run_tracker(
        dry_run=args.dry_run,
        config_path=Path(args.config) if args.config else None,
        history_path=Path(args.data_dir) / "history.csv" if getattr(args, "data_dir", None) else None,
        timeout=args.timeout
    )

    if args.json:
        print(json.dumps(res.to_dict(), indent=2))
    else:
        format_human_output(res)
    return 0


def cmd_test(args) -> int:
    """Handle `test` diagnostic command."""
    success = run_self_test()
    return 0 if success else 1


def cmd_calibrate(args) -> int:
    """Handle `calibrate` log ingestion command."""
    try:
        mix = parse_activity_log(args.csv_file)
        is_dry_run = getattr(args, "dry_run", False)
        
        if args.json:
            print(json.dumps(mix.to_dict(), indent=2))
        else:
            print("\n" + "=" * 60)
            print("📊 OpenRouter Token Mix & Calibration Analysis")
            print("=" * 60)
            print(f" Records processed:       {mix.records_count:,}")
            print(f" Total Prompt Tokens:     {mix.total_prompt_tokens:,} ({mix.weight_prompt*100:.2f}%)")
            print(f" Total Completion Tokens: {mix.total_completion_tokens:,} ({mix.weight_completion*100:.2f}%)")
            print(f" Total Tokens:            {mix.total_tokens:,}")
            print("-" * 60)
            print(f" Calculated Weight Prompt:     {mix.weight_prompt:.6f}")
            print(f" Calculated Weight Completion: {mix.weight_completion:.6f}")
            print("-" * 60)
            print(" 💡 TraceLab Real-World Context (UW TraceLab Dataset):")
            print("    Claude Code / Codex traces report 99.63% in / 0.37% out.")
            print("    Accurate blended weighting reduces token cost anxiety")
            print("    and empowers running premium models responsibly.")
            print("=" * 60)

        if not is_dry_run:
            cfg_path = Path(args.config) if args.config else get_config_path()
            updated_path = update_config_weights(mix.weight_prompt, mix.weight_completion, cfg_path)
            print(f"✅ Configuration calibrated & saved at: {updated_path}\n")
        else:
            print("ℹ️ [DRY RUN] Configuration was not modified.\n")
        return 0
    except Exception as e:
        print(f"Error parsing activity log: {e}", file=sys.stderr)
        return 1


def cmd_model(args) -> int:
    """Handle `model` subcommands (add, remove, list, discover)."""
    action = getattr(args, "model_action", None)
    cfg_path = Path(args.config) if getattr(args, "config", None) else None

    if action == "add":
        res = add_model(
            model_id=args.model_id,
            dry_run=args.dry_run,
            config_path=cfg_path,
            validate_catalog=not args.no_validate
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            icon = "✅" if res.status == "success" else "⚠️"
            print(f"\n{icon} {res.message}")
            print(f"📋 Current Shortlist ({len(res.shortlist)} models):")
            for m in res.shortlist:
                print(f"  • {m}")
            print(f"⚙️ Config: {res.config_path}\n")
        return 0 if res.status in ("success", "warning") else 1

    elif action == "remove":
        res = remove_model(
            model_id=args.model_id,
            dry_run=args.dry_run,
            config_path=cfg_path
        )
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            icon = "✅" if res.status == "success" else "❌"
            print(f"\n{icon} {res.message}")
            print(f"📋 Current Shortlist ({len(res.shortlist)} models):")
            for m in res.shortlist:
                print(f"  • {m}")
            print(f"⚙️ Config: {res.config_path}\n")
        return 0 if res.status == "success" else 1

    elif action == "list":
        res = list_models(config_path=cfg_path)
        if getattr(args, "json", False):
            print(json.dumps(res.to_dict(), indent=2))
        else:
            print(f"\n📋 Shortlisted Models ({len(res.shortlist)}):")
            print(f"⚙️ Config: {res.config_path}")
            print("-" * 50)
            for idx, m in enumerate(res.shortlist, 1):
                badge = " (Default Model)" if idx == 1 else ""
                print(f" {idx}. {m}{badge}")
            print("-" * 50 + "\n")
        return 0

    elif action == "discover":
        cfg = load_config(cfg_path)
        w_in = cfg.get("weight_prompt", 0.9971)
        w_out = cfg.get("weight_completion", 0.0029)

        catalog = fetch_catalog(weight_prompt=w_in, weight_completion=w_out)
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
        format_discovery_output(filtered, json_mode=args.json)
        return 0

    return 0


def main() -> None:
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        prog="anticharon",
        description="Anticharon — The ferryman who minimizes the fare instead of demanding toll."
    )
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--test", action="store_true", help="Run self-test diagnostic suite")

    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Fetch prices, update history, and display report")
    run_parser.add_argument("--dry-run", action="store_true", help="Do not write updates to history.csv")
    run_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    run_parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    run_parser.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    run_parser.add_argument("--data-dir", type=str, default=None, help="Directory to store history.csv")

    # Command: check (alias for run --dry-run)
    check_parser = subparsers.add_parser("check", help="Check current prices without updating history.csv")
    check_parser.add_argument("--dry-run", action="store_true", default=True, help="Do not write updates to history.csv")
    check_parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    check_parser.add_argument("--timeout", type=float, default=10.0, help="HTTP request timeout in seconds")
    check_parser.add_argument("--config", type=str, default=None, help="Path to custom shortlist.json")
    check_parser.add_argument("--data-dir", type=str, default=None, help="Directory to store history.csv")

    # Command: test
    test_parser = subparsers.add_parser("test", help="Run pre-flight self-test and connectivity diagnostics")

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

    # Command: model (add, remove, list, discover)
    model_parser = subparsers.add_parser("model", help="Manage shortlisted models and discover OpenRouter catalog")
    model_subparsers = model_parser.add_subparsers(dest="model_action", help="Model actions")

    # model add
    add_p = model_subparsers.add_parser("add", help="Add a model to shortlist.json")
    add_p.add_argument("model_id", type=str, help="Model ID (e.g. google/gemini-3.7-flash)")
    add_p.add_argument("--dry-run", action="store_true", help="Preview updated shortlist without saving to disk")
    add_p.add_argument("--no-validate", action="store_true", help="Skip live OpenRouter catalog slug validation")
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
        help="Search and filter OpenRouter's model catalog with multi-criteria filters",
        description="Search OpenRouter catalog (~417+ models) with multi-criteria keywords, modality, and price filters."
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

    args = parser.parse_args()

    if args.test or args.command == "test":
        sys.exit(cmd_test(args))

    if args.command in ("run", "check"):
        sys.exit(cmd_run(args))

    if args.command == "calibrate":
        sys.exit(cmd_calibrate(args))

    if args.command == "model":
        sys.exit(cmd_model(args))

    # Default if no command given: run
    if len(sys.argv) == 1:
        res = run_tracker(dry_run=False)
        format_human_output(res)
        sys.exit(0)

    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()

