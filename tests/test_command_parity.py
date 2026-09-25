"""MCP-11 CLI/MCP parity, including W4 tools and registered asymmetries."""

import argparse
import inspect

import pytest

from anticharon import mcp
from anticharon.cli import build_parser
from anticharon.prompts import PROMPTS

# Flags/params intentionally excluded from the reflective comparison, each
# tied to a ledger asymmetry or an already-documented §3a mapping -- not a
# gap to close here.
_ALWAYS_CLI_ONLY = {
    "json", "hints",          # A-3: --json/--hints only in CLI (MCP is always JSON, always has _hints)
    "config", "data_dir", "hermes_config", "no_hermes",  # A-4: per-call path overrides only in CLI
}

# (cli_command, mcp_tool_name, extra_cli_only_dests, extra_mcp_only_params, cli_dest_to_mcp_param_renames)
PARITY_ROWS = [
    (
        "check", "check_prices",
        {"history_csv"},  # raw CSV dump is a CLI display mode, not a data parameter
        set(),
        {},
    ),
    (
        "run", "run_prices",
        {"history_csv", "timeout", "profile", "analytics"},  # --timeout: A-4 (network knob, CLI-only); --profile/--analytics: CLI-only display toggle, no MCP data equivalent
        set(),
        {"zdr": "zdr_only"},
    ),
    (
        "history", "get_model_history",
        {"profile", "analytics", "csv", "history_csv"},  # ledger §3a: CLI's --csv/--history-csv IS the `format` param's CLI shape
        {"format"},
        {},
    ),
    ("model add", "add_model", set(), set(), {}),
    ("model remove", "remove_model", set(), set(), {}),
    ("model list", "list_models", set(), set(), {}),
    ("test", "self_test", set(), set(), {}),
    ("calibrate", "calibrate_token_weights", set(), set(), {"csv_file": "csv_path"}),
    ("model sync", "import_hermes_models", set(), set(), {"hermes_config": "hermes_config_path"}),
]

# A-1 is intentionally MCP-only: hosts that cannot expose the log path use
# three derived weights. A-3/A-4/A-8 are applied in PARITY_ROWS and the
# reflective comparison below. A-5 records that server launch/help are CLI
# surfaces while MCP exposes its native listings and the llms.txt briefing.
REGISTERED_ASYMMETRIES = {
    "A-1": "calibrate_fast accepts host-derived weights when a server-local CSV path is unavailable",
    "A-3": "CLI-only JSON and hints switches; MCP is always structured JSON with hints",
    "A-4": "per-call local path and runtime overrides are CLI-only except Hermes import path",
    "A-5": "help and server launch are CLI-only; MCP uses native listings and llms.txt",
    "A-8": "flat MCP tool names use domain suffixes while CLI commands are namespaced",
}


def _mcp_tool_params(name: str) -> set[str]:
    return set(inspect.signature(getattr(mcp, name)).parameters)


def _cli_dests(subparsers, command: str) -> set[str]:
    if " " in command:
        parent, child = command.split(" ", 1)
        parser = subparsers.choices[parent]
        model_subparsers = next(action for action in parser._actions if isinstance(action, argparse._SubParsersAction))
        return {a.dest for a in model_subparsers.choices[child]._actions if a.dest not in ("help", "==SUPPRESS==")}
    return {a.dest for a in subparsers.choices[command]._actions if a.dest not in ("help", "==SUPPRESS==")}


def test_check_history_run_mcp_tools_are_registered():
    """New tool added to mcp.py without a PARITY_ROWS entry should fail here,
    not slip through silently."""
    covered = {row[1] for row in PARITY_ROWS}
    required = {"check_prices", "run_prices", "get_model_history", "add_model", "remove_model", "list_models", "self_test", "calibrate_token_weights", "import_hermes_models"}
    assert covered == required
    assert set(REGISTERED_ASYMMETRIES) == {"A-1", "A-3", "A-4", "A-5", "A-8"}


@pytest.mark.parametrize("cli_command,mcp_tool,cli_only,mcp_only,renames", PARITY_ROWS)
def test_cli_mcp_parameter_sets_match(cli_command, mcp_tool, cli_only, mcp_only, renames):
    _, subparsers, _ = build_parser()
    cli_dests = _cli_dests(subparsers, cli_command)
    mcp_params = _mcp_tool_params(mcp_tool)

    excluded = (_ALWAYS_CLI_ONLY - renames.keys()) | cli_only
    mapped_cli = {renames.get(d, d) for d in cli_dests if d not in excluded}
    mapped_mcp = mcp_params - mcp_only

    assert mapped_cli == mapped_mcp, (
        f"{cli_command!r} <-> {mcp_tool!r} parameter mismatch: "
        f"cli-only={mapped_cli - mapped_mcp}, mcp-only={mapped_mcp - mapped_cli}"
    )


def test_every_registered_tool_declares_all_five_annotations():
    import asyncio

    tools = asyncio.run(mcp.server.list_tools())
    assert tools
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.title
        assert tool.annotations.read_only_hint is not None
        assert tool.annotations.destructive_hint is not None
        assert tool.annotations.idempotent_hint is not None
        assert tool.annotations.open_world_hint is not None


def test_prompt_registry_covers_five_mcp_prompts():
    import asyncio

    prompts = asyncio.run(mcp.server.list_prompts())
    assert {prompt.name for prompt in prompts} == set(PROMPTS)


def test_server_identity_has_version_and_instructions():
    assert mcp.server.version == mcp.__version__
    assert "anticharon://llms.txt" in mcp.server.instructions
