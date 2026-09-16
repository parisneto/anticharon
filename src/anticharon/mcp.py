"""Model Context Protocol (MCP) server implementation for Anticharon.

Exposes price monitoring, 30-day historical analytics, catalog discovery,
and Hermes model synchronization tools, resources, and prompts over stdio.
"""

import importlib.resources as pkg_resources
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from anticharon import __version__
from anticharon.config import get_config_path, get_history_path, load_config
from anticharon.discovery import fetch_catalog, filter_catalog
from anticharon.hermes import get_hermes_models, sync_hermes_to_config
from anticharon.storage import CSV_HEADER
from anticharon.tracker import run_tracker

# Initialize MCP Server instance
server = MCPServer("anticharon")


# ==============================================================================
# MCP Tools
# ==============================================================================

@server.tool(
    name="check_prices",
    description=(
        "Fetches current OpenRouter model pricing for your monitored shortlist, calculates "
        "calibrated blended price per 1M tokens, computes 7-day moving averages, evaluates "
        "volatility alerts (PRICE_SPIKE, PRICE_DROP, BEST_OPTION_CHANGED), and attaches "
        "30-day analytical intelligence profiles (STABLE, PROMO_ENDED, SUNSETTING, etc.). "
        "Maintains a compact local shortlist.json and history.csv to help your agents switch "
        "models seamlessly, optimize budgets, and minimize the ferryman's token toll."
    )
)
def check_prices(
    force_refresh: bool = False,
    dry_run: bool = True,
    include_analytics: bool = True,
    zdr_only: bool = False
) -> Dict[str, Any]:
    """Execute price monitoring check and return structured intelligence."""
    res = run_tracker(
        dry_run=dry_run,
        enable_analytics=include_analytics,
        hints_enabled=True,
        timeout=10.0 if not force_refresh else 15.0,
        zdr_only=zdr_only
    )
    return res.to_dict()


@server.tool(
    name="get_model_history",
    description=(
        "Audits 30-day historical price trajectories, statistical volatility (CV%), "
        "directional trend sparklines, deterministic intelligence profiles, and sibling "
        "alternative recommendations from local history.csv storage, giving your agent "
        "the empirical intelligence to navigate price spikes and vendor rate increases."
    )
)
def get_model_history(
    model_id: Optional[str] = None,
    format: str = "json"
) -> Dict[str, Any]:
    """Return historical intelligence in JSON format or raw CSV table."""
    hist_path = get_history_path()

    if format.lower() == "csv":
        content = hist_path.read_text(encoding="utf-8").strip() if hist_path.exists() else CSV_HEADER
        return {
            "status": "success",
            "format": "csv",
            "path": str(hist_path),
            "data": content
        }

    res = run_tracker(
        dry_run=True,
        enable_analytics=True,
        hints_enabled=True
    )
    payload = res.to_dict()

    if model_id:
        target = model_id.strip().lower()
        filtered_shortlist = [
            p for p in payload.get("prices_shortlist", [])
            if target in p.get("model", "").lower()
        ]
        payload["prices_shortlist"] = filtered_shortlist
        payload["target_model"] = model_id

    return payload


@server.tool(
    name="discover_models",
    description=(
        "Queries and filters OpenRouter's live catalog (~417+ models) using multi-criteria "
        "keywords, promotional/free flags (:free, $0.00), output modality, and price ceiling "
        "expressions, calculating real-world blended prices per 1M tokens."
    )
)
def discover_models(
    query: Optional[str] = None,
    promo_only: bool = False,
    modality: str = "text",
    max_price: Optional[float] = None,
    limit: int = 15
) -> Dict[str, Any]:
    """Query live catalog and return matching models with blended pricing."""
    cfg = load_config()
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
        query=query,
        promo_only=promo_only,
        modality=modality,
        max_price=max_price
    )

    matches = [m.to_dict() for m in filtered[:limit]]
    return {
        "status": "success",
        "total_matches": len(filtered),
        "returned_count": len(matches),
        "query": query,
        "promo_only": promo_only,
        "max_price": max_price,
        "models": matches,
        "_hints": {
            "blended_price_1m": "Weighted price per 1M tokens based on agent prompt/completion mix (99.71% in / 0.29% out)",
            "is_promo": "True if model is on promotion or 100% free (:free, $0.00)",
            "prompt_price_1m": "Input cost per 1M tokens",
            "completion_price_1m": "Output cost per 1M tokens"
        }
    }


@server.tool(
    name="import_hermes_models",
    description=(
        "Imports active default and fallback models from Hermes Agent configuration "
        "(~/.hermes/config.yaml or $HERMES_HOME) into Anticharon's shortlist. "
        "READ-ONLY ON HERMES: Never modifies Hermes configuration. "
        "Default is dry_run=True (preview only); set dry_run=False to write to Anticharon shortlist.json."
    )
)
def import_hermes_models(
    hermes_config_path: Optional[str] = None,
    dry_run: bool = True
) -> Dict[str, Any]:
    """Import Hermes active models into Anticharon shortlist.json."""
    hermes_info = get_hermes_models(custom_path=hermes_config_path, prompt_if_missing=False)
    if not hermes_info:
        return {
            "status": "warning",
            "detected": False,
            "direction": "hermes→anticharon",
            "hermes_untouched": True,
            "message": "Hermes configuration not found at ~/.hermes/config.yaml or via $HERMES_HOME.",
            "hint": "Specify hermes_config_path parameter or ensure ~/.hermes/config.yaml is present."
        }

    changed, new_shortlist, saved_path = sync_hermes_to_config(
        hermes_info, dry_run=dry_run
    )

    if dry_run:
        notice = "ℹ️ PREVIEW ONLY: Hermes models detected but Anticharon shortlist was not modified. Pass dry_run=False to persist."
    elif changed:
        notice = "💾 SHORTLIST UPDATED: Hermes models successfully written to Anticharon shortlist."
    else:
        notice = "✅ SHORTLIST UP TO DATE: Anticharon shortlist already matches Hermes models."

    return {
        "status": "success",
        "direction": "hermes→anticharon",
        "hermes_untouched": True,
        "detected": True,
        "source": hermes_info.get("source"),
        "method": hermes_info.get("method"),
        "default_model": hermes_info.get("default_model"),
        "models_count": len(hermes_info.get("all_models", [])),
        "changed": changed,
        "dry_run": dry_run,
        "notice": notice,
        "shortlist": new_shortlist,
        "config_path": str(saved_path)
    }


# ==============================================================================
# MCP Resources
# ==============================================================================

@server.resource("anticharon://llms.txt", mime_type="text/markdown")
def resource_llms_txt() -> str:
    """Agent-to-Agent (A2A) discovery briefing and schema documentation."""
    try:
        content = pkg_resources.files("anticharon").joinpath("llms.txt").read_text(encoding="utf-8").strip()
        return content
    except Exception:
        pass

    candidates = [
        Path(__file__).resolve().parent / "llms.txt",
        Path(__file__).resolve().parent.parent.parent / "llms.txt",
        Path.home() / ".anticharon" / "llms.txt"
    ]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8").strip()

    return "# Anticharon Price Optimizer\nOpenRouter model price tracker and token cost optimizer."


@server.resource("anticharon://history.csv", mime_type="text/csv")
def resource_history_csv() -> str:
    """Raw 30-day sliding history table."""
    hist_path = get_history_path()
    if hist_path.exists():
        return hist_path.read_text(encoding="utf-8").strip()
    return CSV_HEADER


@server.resource("anticharon://shortlist.json", mime_type="application/json")
def resource_shortlist_json() -> str:
    """Active model shortlist and calibrated weights configuration."""
    cfg_path = get_config_path()
    if cfg_path.exists():
        return cfg_path.read_text(encoding="utf-8").strip()
    return json.dumps(load_config(), indent=2)


# ==============================================================================
# MCP Prompts
# ==============================================================================

@server.prompt(
    name="cost_spike_triage",
    description="Guidance for evaluating a PRICE_SPIKE or PROMO_ENDED alert and recommending cheaper models."
)
def cost_spike_triage(model_id: str, current_price: float, ma_7d: float) -> str:
    """Prompt template for triaging a sudden price increase."""
    return (
        f"Anticharon detected a significant price increase on model '{model_id}'.\n"
        f"Current Price per 1M tokens: ${current_price:.5f}\n"
        f"7-Day Moving Average: ${ma_7d:.5f}\n\n"
        f"Please analyze this price jump:\n"
        f"1. Check if an introductory promotion ended or vendor raised rates.\n"
        f"2. Use tool `discover_models` or `check_prices` to identify cheaper alternatives in the same family.\n"
        f"3. Recommend whether to switch Hermes default model or reorder fallback_providers."
    )


@server.prompt(
    name="model_migration_advisor",
    description="Guidance for evaluating a SUNSETTING model profile and migrating to a newer sibling model."
)
def model_migration_advisor(legacy_model: str, recommended_model: str) -> str:
    """Prompt template for migrating from a sunsetting model."""
    return (
        f"Anticharon flagged model '{legacy_model}' with a SUNSETTING profile.\n"
        f"A newer version in the same model family ('{recommended_model}') is available at an equal or lower cost.\n\n"
        f"Please formulate an action plan:\n"
        f"1. Compare performance characteristics of '{recommended_model}' vs '{legacy_model}'.\n"
        f"2. Validate that '{recommended_model}' is compatible with active agent tool schemas.\n"
        f"3. Provide the exact Hermes CLI command to switch the default model: `hermes config set model.default \"{recommended_model}\"`."
    )


@server.prompt(
    name="family_upgrade_discover",
    description="Discovers newer generation models in the same provider family (e.g. Gemini, DeepSeek, Qwen) and evaluates cost-benefit migration."
)
def family_upgrade_discover(model_or_family: str) -> str:
    """Prompt template for discovering newer sibling models in the same provider family."""
    return (
        f"Anticharon agent workflow: Discover newer version models in family '{model_or_family}'.\n\n"
        f"Execution Plan:\n"
        f"1. Run tool `discover_models(query=\"{model_or_family}\")` to find all active catalog models in this family.\n"
        f"2. Identify newer generations or sibling variants (e.g. 3.8 vs 3.7, flash vs flash-lite, coder vs chat).\n"
        f"3. Compare calibrated blended pricing per 1M tokens against current rates.\n"
        f"4. If a newer model is cheaper or equal in cost, formulate an upgrade recommendation:\n"
        f"   - Compare context windows and benchmark strengths.\n"
        f"   - Provide the CLI command: `hermes config set model.default \"<new_model_slug>\"`.\n"
        f"   - Offer to add it to shortlist: `anticharon model add \"<new_model_slug>\"`."
    )


@server.prompt(
    name="daily_cost_briefing",
    description="Generates an executive daily cost briefing of model prices, moving averages, and volatility alerts across the active shortlist."
)
def daily_cost_briefing(budget_threshold: float = 0.50) -> str:
    """Prompt template for daily cost monitoring and executive summary."""
    return (
        f"Anticharon agent workflow: Executive Daily Cost Briefing (Threshold: ${budget_threshold:.2f}/1M tokens).\n\n"
        f"Execution Plan:\n"
        f"1. Call tool `check_prices(dry_run=true, include_analytics=true)`.\n"
        f"2. Check for any active price warnings (e.g. `BEST_OPTION_CHANGED`, `PRICE_SPIKE`, `PRICE_DROP`).\n"
        f"3. Identify models exceeding ${budget_threshold:.2f} per 1M blended tokens.\n"
        f"4. Produce a concise 3-bullet briefing:\n"
        f"   • 🏆 Cheapest Workhorse Model right now\n"
        f"   • ⚠️ Volatility & Alerts (spikes, expired promos, or default model surpassed)\n"
        f"   • 💡 Actionable Recommendation for today's LLM agent orchestration"
    )


@server.prompt(
    name="budget_optimization_audit",
    description="Audits the active shortlist to identify cost outliers, SUNSETTING legacy versions, and opportunities to reorder fallback providers."
)
def budget_optimization_audit() -> str:
    """Prompt template for comprehensive shortlist budget audit."""
    return (
        "Anticharon agent workflow: Comprehensive Shortlist Budget Audit.\n\n"
        "Execution Plan:\n"
        "1. Call tool `get_model_history()` to inspect 30-day trajectories and intelligence profiles.\n"
        "2. Classify models by budget tier:\n"
        "   - Identify models classified as 🛡️ STABLE (low budget risk).\n"
        "   - Flag models classified as 📈 PROMO_ENDED or ⚠️ SUNSETTING.\n"
        "   - Flag models with high CV% volatility (⚡ VOLATILE).\n"
        "3. For any expensive or sunsetting model, run `discover_models` to find drop-in replacements.\n"
        "4. Recommend optimal Hermes `fallback_providers` ordering (cheapest reliable providers first)."
    )


# ==============================================================================
# Server Entrypoint
# ==============================================================================

def run_mcp_server(transport: str = "stdio") -> None:
    """Launch the Anticharon MCP server with strict stdio hygiene."""
    # Direct all internal logging strictly to stderr to prevent stdio JSON-RPC corruption
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s: %(message)s")

    # If launched directly in an interactive terminal, provide helpful guidance on stderr
    if sys.stdin.isatty():
        sys.stderr.write(
            f"\n🪙 Anticharon MCP Server (v{__version__}) running over {transport}.\n"
            f"📡 Listening for JSON-RPC 2.0 frames on stdio...\n"
            f"💡 Tip: This server is designed to be orchestrated by an MCP host (Hermes Agent, Cursor, Claude Desktop).\n"
            f"🛑 Press Ctrl+C to terminate cleanly.\n\n"
        )
        sys.stderr.flush()

    try:
        server.run(transport=transport)
    except KeyboardInterrupt:
        sys.stderr.write("\n🛑 Anticharon MCP server terminated cleanly.\n")
        sys.stderr.flush()
