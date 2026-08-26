"""Command-line interface (CLI) for Anticharon."""

import argparse
import json
import sys
from pathlib import Path

from anticharon import __version__
from anticharon.config import update_config_weights, get_config_path
from anticharon.log_parser import parse_activity_log
from anticharon.tester import run_self_test
from anticharon.tracker import run_tracker


def format_human_output(result) -> None:
    """Format and print human-readable CLI summary."""
    print("\n" + "=" * 65)
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
    print("=" * 65)

    print(f"{'MODEL':<38} {'PRICE/1M':<12} {'MA 7D':<12} {'CHANGE (7D)':<10}")
    print("-" * 74)

    for p in result.prices_shortlist:
        change_str = f"{p.change_vs_7d_pct:+.1f}%" if p.change_vs_7d_pct != 0 else "0.0%"
        print(f"{p.model:<38} ${p.price_1m:<11.5f} ${p.ma_7d:<11.5f} {change_str:<10}")

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
    print("=" * 65 + "\n")


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

    args = parser.parse_args()

    if args.test or args.command == "test":
        sys.exit(cmd_test(args))

    if args.command in ("run", "check"):
        sys.exit(cmd_run(args))

    if args.command == "calibrate":
        sys.exit(cmd_calibrate(args))

    # Default if no command given: run
    if len(sys.argv) == 1:
        res = run_tracker(dry_run=False)
        format_human_output(res)
        sys.exit(0)

    parser.print_help()
    sys.exit(0)


if __name__ == "__main__":
    main()
