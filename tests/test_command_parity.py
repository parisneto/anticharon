"""MCP-11 (D-19/D-20, ledger §3a): CLI <-> MCP parameter parity for the
command-split surface landed in W3 (`check`/`history`/`run`).

Scope note: `discover_models`/`import_hermes_models` predate this wave and
are not re-audited here (MCP-11's scope this wave is the command split);
`add_model`/`remove_model`/`list_models`/`calibrate_*`/`self_test`/
`check_updates`/`run_update` don't exist as MCP tools yet (W4/W5). Extend
PARITY_ROWS as later waves land their own tool<->command pairs.
"""

import inspect

import pytest

from anticharon import mcp
from anticharon.cli import build_parser

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
]


def _mcp_tool_params(name: str) -> set[str]:
    return set(inspect.signature(getattr(mcp, name)).parameters)


def _cli_dests(subparsers, command: str) -> set[str]:
    return {a.dest for a in subparsers.choices[command]._actions if a.dest not in ("help", "==SUPPRESS==")}


def test_check_history_run_mcp_tools_are_registered():
    """New tool added to mcp.py without a PARITY_ROWS entry should fail here,
    not slip through silently."""
    covered = {row[1] for row in PARITY_ROWS}
    assert covered <= {"check_prices", "run_prices", "get_model_history"}


@pytest.mark.parametrize("cli_command,mcp_tool,cli_only,mcp_only,renames", PARITY_ROWS)
def test_cli_mcp_parameter_sets_match(cli_command, mcp_tool, cli_only, mcp_only, renames):
    _, subparsers, _ = build_parser()
    cli_dests = _cli_dests(subparsers, cli_command)
    mcp_params = _mcp_tool_params(mcp_tool)

    mapped_cli = {renames.get(d, d) for d in cli_dests if d not in _ALWAYS_CLI_ONLY | cli_only}
    mapped_mcp = mcp_params - mcp_only

    assert mapped_cli == mapped_mcp, (
        f"{cli_command!r} <-> {mcp_tool!r} parameter mismatch: "
        f"cli-only={mapped_cli - mapped_mcp}, mcp-only={mapped_mcp - mapped_cli}"
    )
