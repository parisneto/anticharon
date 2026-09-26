"""Model Context Protocol (MCP) server implementation for Anticharon.

Exposes price monitoring, 30-day historical analytics, catalog discovery,
and Hermes model synchronization tools, resources, and prompts over stdio.
"""

import contextlib
import csv
import importlib.resources as pkg_resources
import inspect
import io
import json
import logging
import math
import sys
import time
from pathlib import Path
from typing import Any

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from mcp.types import CallToolResult, TextContent, ToolAnnotations

from anticharon import __version__
from anticharon.config import (
    get_config_path,
    get_history_path,
    load_config,
    update_config_weights,
)
from anticharon.discovery import fetch_catalog, filter_catalog
from anticharon.hermes import build_hermes_import_payload, get_hermes_models
from anticharon.log_parser import parse_activity_log
from anticharon.manager import add_model as manage_add_model
from anticharon.manager import list_models as manage_list_models
from anticharon.manager import remove_model as manage_remove_model
from anticharon.models import ERROR_STATUSES, AgentMessage, build_envelope
from anticharon.prompts import PROMPTS, render_prompt
from anticharon.storage import CSV_HEADER
from anticharon.tracker import read_check_result, read_history_result, run_tracker

# Initialize MCP Server instance
server = MCPServer(
    "anticharon",
    version=__version__,
    instructions=(
        "Anticharon tracks OpenRouter model prices and shortlist history. Read "
        "anticharon://llms.txt for the operational glossary and call check_prices "
        "before recommending a default model."
    ),
)


def _annotations(title: str, read_only: bool, destructive: bool, idempotent: bool, open_world: bool) -> ToolAnnotations:
    """Declare all standard risk hints for an MCP tool."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=read_only,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=open_world,
    )


def _message(level: str, code: str, text: str) -> AgentMessage:
    """Build the shared agent-message type used by response envelopes."""
    return AgentMessage(level, code, text)


def tool_result(envelope: dict[str, Any]) -> dict[str, Any] | CallToolResult:
    """Return an enveloped payload as an MCP tool result (spec §10.1a, A2A-3).

    `status` in ERROR_STATUSES becomes a tool execution error (`isError: true`)
    carrying the same JSON body, so hosts hand it to the model for
    self-correction (MCP spec 2026-07-28, Tools -> Error Handling). Anything
    else is an ordinary result. Tools keep their `dict[str, Any]` annotation:
    the SDK rejects `CallToolResult` inside a Union and passes a returned
    `CallToolResult` through unchanged.
    """
    if envelope["status"] not in ERROR_STATUSES:
        return envelope
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(envelope, indent=2, ensure_ascii=False))],
        structured_content=envelope,
        is_error=True,
    )


# ==============================================================================
# MCP Tools
# ==============================================================================

@server.tool(
    name="check_prices",
    annotations=_annotations("Check prices", True, False, True, False),
    description=(
        "Local read (no network) of the latest normalized/blended price per your monitored "
        "shortlist, computes 7-day moving averages, and shows price alerts (PRICE_SPIKE, "
        "PRICE_DROP, BEST_OPTION_CHANGED) exactly as persisted by the last `run_prices` call -- "
        "never recomputed here. Source: history.csv (compact summary) and alerts.json. Call "
        "`run_prices` first to refresh; this tool never fetches from OpenRouter. See "
        "anticharon://llms.txt for the authoritative glossary."
    )
)
def check_prices(model_id: str | None = None) -> dict[str, Any]:
    """Local-only latest-price + persisted-alerts read (D-19)."""
    started = time.perf_counter()
    res = read_check_result(model_id=model_id, hints_enabled=True)
    return tool_result(build_envelope(res.to_dict(), res.messages, started))


@server.tool(
    name="run_prices",
    annotations=_annotations("Run price update", False, False, True, True),
    description=(
        "Fetches current OpenRouter model pricing for your monitored shortlist, writes "
        "history.csv and effective_prices.json, and pre-computes + persists price alerts "
        "(PRICE_SPIKE, PRICE_DROP, BEST_OPTION_CHANGED) into alerts.json. Saves by default; "
        "pass dry_run=true to compute without persisting. `model_id` exact-filters the "
        "configured shortlist (refuses NOT_MONITORED for an absent slug, no catalog lookup); "
        "without it, the whole shortlist is updated, skipping models already refreshed today "
        "unless force=true. `zdr_only` adds a live, never-persisted Zero Data Retention policy "
        "price for this response only (D-28). See anticharon://llms.txt for the authoritative glossary."
    )
)
def run_prices(
    model_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    zdr_only: bool = False,
) -> dict[str, Any]:
    """Execute the fetch-and-persist price update and return structured intelligence."""
    started = time.perf_counter()
    res = run_tracker(
        dry_run=dry_run,
        model_id=model_id,
        force=force,
        zdr_only=zdr_only,
        hints_enabled=True,
    )
    return tool_result(build_envelope(res.to_dict(), res.messages, started))


@server.tool(
    name="get_model_history",
    annotations=_annotations("Get model history", True, False, True, False),
    description=(
        "Local read (no network) of 30-day historical price trajectories, statistical "
        "volatility (CV%), directional trend sparklines, deterministic intelligence profiles, "
        "and sibling alternative recommendations, derived from history.csv's d1..d30 columns "
        "(themselves derived from effective_prices.json by the last `run_prices` call). See "
        "anticharon://llms.txt for the authoritative glossary."
    )
)
def get_model_history(
    model_id: str | None = None,
    format: str = "json"
) -> dict[str, Any]:
    """Return historical intelligence in JSON format or raw CSV table."""
    started = time.perf_counter()
    if format.lower() == "csv":
        hist_path = get_history_path()
        content = hist_path.read_text(encoding="utf-8").strip() if hist_path.exists() else CSV_HEADER
        return tool_result(build_envelope({
            "status": "success",
            "format": "csv",
            "path": str(hist_path),
            "data": content
        }, [], started))

    res = read_history_result(model_id=model_id, hints_enabled=True)
    return tool_result(build_envelope(res.to_dict(), res.messages, started))


@server.tool(
    name="discover_models",
    annotations=_annotations("Discover models", True, False, True, True),
    description=(
        "Queries and filters OpenRouter's live catalog (~417+ models) using multi-criteria "
        "keywords, promotional/free flags (:free, $0.00), output modality, and price ceiling "
        "expressions, calculating real-world blended prices per 1M tokens. See "
        "anticharon://llms.txt for the authoritative glossary."
    )
)
def discover_models(
    query: str | None = None,
    promo_only: bool = False,
    modality: str = "text",
    max_price: float | None = None,
    limit: int = 15
) -> dict[str, Any]:
    """Query live catalog and return matching models with blended pricing."""
    started = time.perf_counter()
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
    return tool_result(build_envelope({
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
    }, [], started))


@server.tool(
    name="import_hermes_models",
    annotations=_annotations("Import Hermes models", False, False, True, False),
    description=(
        "Imports active default and fallback models from Hermes Agent configuration "
        "(~/.hermes/config.yaml or $HERMES_HOME) into Anticharon's shortlist. "
        "READ-ONLY ON HERMES: Never modifies Hermes configuration. "
        "Saves to Anticharon shortlist.json by default; pass dry_run=true to preview without writing. "
        "See anticharon://llms.txt for the authoritative glossary."
    )
)
def import_hermes_models(
    hermes_config_path: str | None = None,
    dry_run: bool = False
) -> dict[str, Any]:
    """Import Hermes active models into Anticharon shortlist.json."""
    started = time.perf_counter()
    hermes_info = get_hermes_models(custom_path=hermes_config_path, prompt_if_missing=False)
    payload, messages = build_hermes_import_payload(hermes_info, dry_run=dry_run)
    return tool_result(build_envelope(payload, messages, started))


@server.tool(
    name="add_model",
    annotations=_annotations("Add model", False, False, True, True),
    description=(
        "Validates an exact model slug against OpenRouter's live catalog and adds it to "
        "shortlist.json. Saves by default; pass dry_run=true to preview. If the catalog "
        "is unavailable, nothing is saved and CATALOG_UNAVAILABLE asks you to retry later. "
        "See anticharon://llms.txt for the authoritative glossary."
    ),
)
def add_model(model_id: str, dry_run: bool = False, default: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    result = manage_add_model(model_id, dry_run=dry_run, default=default)
    return tool_result(build_envelope(result.to_dict(), result.messages, started))


@server.tool(
    name="remove_model",
    annotations=_annotations("Remove model", False, True, True, False),
    description=(
        "Removes a manually managed model from shortlist.json. Saves by default; "
        "pass dry_run=true to preview. Hermes-managed models are refused with SOURCE_MANAGED. "
        "See anticharon://llms.txt for the authoritative glossary."
    ),
)
def remove_model(model_id: str, dry_run: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    result = manage_remove_model(model_id, dry_run=dry_run)
    return tool_result(build_envelope(result.to_dict(), result.messages, started))


@server.tool(
    name="list_models",
    annotations=_annotations("List models", True, False, True, False),
    description=("Reads the local shortlist and returns each model's source, default status, and known canonical slug. "
                 "See anticharon://llms.txt for the authoritative glossary."),
)
def list_models() -> dict[str, Any]:
    started = time.perf_counter()
    result = manage_list_models()
    return tool_result(build_envelope(result.to_dict(), result.messages, started))


@server.tool(
    name="self_test",
    annotations=_annotations("Run self test", False, False, True, True),
    description=("Runs the same diagnostics as `anticharon test`, including Hermes integration and optional connectivity. "
                 "See anticharon://llms.txt for the authoritative glossary."),
)
def self_test() -> dict[str, Any]:
    from anticharon.tester import run_self_test

    started = time.perf_counter()
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        ok = run_self_test(json_mode=True)
    try:
        report = json.loads(captured.getvalue())
    except json.JSONDecodeError:
        report = {"status": "success" if ok else "error", "all_passed": bool(ok)}
    payload = {key: value for key, value in report.items() if key not in {"status", "messages", "elapsed_ms"}}
    payload["status"] = "success" if ok else "error"
    messages = [AgentMessage(**message) for message in report.get("messages", []) if message.get("code") != "COMPLETED"]
    if not ok and not any(message.code == "SELF_TEST_FAILED" for message in messages):
        messages.append(_message("error", "SELF_TEST_FAILED", "One or more self-test checks failed."))
    return tool_result(build_envelope(payload, messages, started))


@server.tool(
    name="calibrate_token_weights",
    annotations=_annotations("Calibrate token weights", False, False, True, False),
    description=(
        "Reads an activity CSV path accessible to the MCP server and derives the three token "
        "weights locally. Saves by default, first copying shortlist.json to shortlist.json.bak; "
        "pass dry_run=true to compute without saving. CSV bytes are never uploaded through MCP. "
        "See anticharon://llms.txt for the authoritative glossary."
    ),
)
def calibrate_token_weights(csv_path: str, dry_run: bool = False) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        mix = parse_activity_log(csv_path)
    except (OSError, UnicodeError, ValueError, csv.Error) as exc:
        messages = [_message("error", "CALIBRATION_INPUT_INVALID", f"Could not read or parse the activity CSV ({type(exc).__name__}); weights were not changed.")]
        return tool_result(build_envelope({"status": "error", "csv_path": Path(csv_path).name}, messages, started))
    config_path = get_config_path()
    backup_path = None
    if not dry_run:
        backup_path = config_path.with_name(config_path.name + ".bak")
        update_config_weights(mix.weight_uncached_prompt, mix.weight_cached_prompt, mix.weight_completion, config_path)
    messages = [_message("info", "CALIBRATION_BACKUP", f"Previous token weights saved to {backup_path}.")] if backup_path else []
    messages.append(_message("info", "PREVIEW_ONLY" if dry_run else "SHORTLIST_UPDATED", "Calibration computed; weights were not saved." if dry_run else "Calibrated token weights were saved."))
    return tool_result(build_envelope({"status": "success", **mix.to_dict(), "dry_run": dry_run, "config_path": str(config_path), "backup_path": str(backup_path) if backup_path else None}, messages, started))


@server.tool(
    name="calibrate_fast",
    annotations=_annotations("Calibrate from weights", False, False, True, False),
    description=(
        "Saves host-derived uncached prompt, cached prompt, and completion weights after finite "
        "[0, 1] and sum validation. Totals within 0.000001 of 1 are normalized and rounded to "
        "six decimals. Saves by default with a .bak copy; pass dry_run=true to preview. "
        "See anticharon://llms.txt for the authoritative glossary."
    ),
)
def calibrate_fast(
    weight_uncached_prompt: float,
    weight_cached_prompt: float,
    weight_completion: float,
    dry_run: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    weights = (weight_uncached_prompt, weight_cached_prompt, weight_completion)
    if any(isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w) or not 0 <= w <= 1 for w in weights):
        return tool_result(build_envelope({"status": "error"}, [_message("error", "CALIBRATION_INPUT_INVALID", "Each weight must be a finite number in [0, 1].")], started))
    total = sum(weights)
    if abs(total - 1.0) > 0.000001 or total == 0:
        return tool_result(build_envelope({"status": "error", "sum": total}, [_message("error", "CALIBRATION_INPUT_INVALID", "The three weights must sum to 1 within 0.000001.")], started))
    normalized = tuple(round(w / total, 6) for w in weights)
    cfg_path = get_config_path()
    backup_path = None
    if not dry_run:
        backup_path = cfg_path.with_name(cfg_path.name + ".bak")
        update_config_weights(*normalized, config_path=cfg_path)
    messages = [_message("info", "CALIBRATION_BACKUP", f"Previous token weights saved to {backup_path}.")] if backup_path else []
    messages.append(_message("info", "PREVIEW_ONLY" if dry_run else "SHORTLIST_UPDATED", "Normalized weights were computed; nothing was saved." if dry_run else "Normalized token weights were saved."))
    return tool_result(build_envelope({"status": "success", "weight_uncached_prompt": normalized[0], "weight_cached_prompt": normalized[1], "weight_completion": normalized[2], "sum": sum(normalized), "dry_run": dry_run, "config_path": str(cfg_path), "backup_path": str(backup_path) if backup_path else None}, messages, started))


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


@server.resource("anticharon://calibration-details", mime_type="text/markdown")
def resource_calibration_details() -> str:
    """Explain the three calibration components, derivation, and local fallback."""
    return (
        "# Token weight calibration\n\n"
        "Anticharon blends uncached prompt, cached prompt, and completion prices. "
        "`weight_uncached_prompt` is the share of all prompt tokens not served from cache; "
        "`weight_cached_prompt` is the cached prompt share; `weight_completion` is the output share.\n\n"
        "For each activity row, use `tokens_prompt`, `tokens_cached`, and `tokens_completion`. "
        "Sum prompt, cached, and completion counts. Uncached prompt = prompt − cached; total = prompt + completion. "
        "Divide each of uncached, cached, and completion counts by total. For example, a row with "
        "1,000 prompt, 600 cached, and 100 completion tokens yields weights 0.363636, 0.545455, and 0.090909.\n\n"
        "Pass the resulting values to `calibrate_fast`; each must be finite and in [0, 1], and their "
        "sum must be within 0.000001 of 1. The tool normalizes that sum and rounds to six decimals. "
        "If the activity CSV is available to this server, `calibrate_token_weights` accepts its local path; "
        "the file contents are not sent over MCP. Otherwise run `anticharon calibrate <csv-path>` locally "
        "and pass the resulting three weights to `calibrate_fast`. Writes save the previous config to `.bak`; "
        "set `dry_run=true` to preview without saving."
    )


# ==============================================================================
# MCP Prompts (rendered by the shared prompt registry)
# ==============================================================================
def _register_prompt(name: str, description: str, renderer) -> None:
    signature = inspect.signature(renderer)
    parameters = [
        inspect.Parameter(
            key, inspect.Parameter.KEYWORD_ONLY, default=parameter.default,
            annotation=parameter.annotation,
        ) if parameter.default is not inspect.Parameter.empty else inspect.Parameter(
            key, inspect.Parameter.KEYWORD_ONLY, annotation=parameter.annotation,
        )
        for key, parameter in signature.parameters.items()
    ]

    def handler(**arguments: Any) -> str:
        return render_prompt(name, arguments)

    handler.__name__ = name
    handler.__signature__ = inspect.Signature(parameters)  # type: ignore[attr-defined]
    handler.__annotations__ = dict(renderer.__annotations__)
    handler.__annotations__["return"] = str
    server.prompt(name=name, description=description)(handler)


for _prompt in PROMPTS.values():
    _register_prompt(_prompt.name, _prompt.description, _prompt.render)


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
