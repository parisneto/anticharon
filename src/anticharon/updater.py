"""User-initiated, experimental self-update operations."""

import json
import os
import shutil
import subprocess
import sys
from enum import Enum
from typing import Any

import requests

from anticharon.models import AgentMessage

LATEST_RELEASE_URL = "https://api.github.com/repos/parisneto/anticharon/releases/latest"
INSTALL_SOURCE = "git+https://github.com/parisneto/anticharon.git"
UPDATE_TIMEOUT_SECONDS = 2.0


class UpdateType(str, Enum):
    """Named update sequences exposed by the MCP schema and CLI."""

    INSTALL_ONLY = "install_only"
    RESTART_HOST = "restart_host"
    PHOENIX = "phoenix"
    PHOENIX_INVERTED = "phoenix_inverted"
    RELOAD_REQUEST = "reload_request"


UPDATE_TYPE_ALIASES = {
    "1": UpdateType.INSTALL_ONLY,
    "2": UpdateType.RESTART_HOST,
    "3": UpdateType.PHOENIX,
    "4": UpdateType.PHOENIX_INVERTED,
    "5": UpdateType.RELOAD_REQUEST,
}


def parse_update_type(value: UpdateType | str | int) -> UpdateType:
    """Accept documented type names and the CLI's legacy numeric aliases."""
    if isinstance(value, UpdateType):
        return value
    normalized = str(value).strip().lower()
    if normalized in UPDATE_TYPE_ALIASES:
        return UPDATE_TYPE_ALIASES[normalized]
    return UpdateType(normalized)


def check_updates(installed_version: str, timeout: float = UPDATE_TIMEOUT_SECONDS) -> tuple[dict[str, Any], list[AgentMessage]]:
    """Compare an installed version to GitHub's latest release with a hard timeout."""
    try:
        response = requests.get(
            LATEST_RELEASE_URL,
            headers={"Accept": "application/vnd.github+json"},
            timeout=timeout,
        )
        if response.status_code != 200:
            raise RuntimeError(f"GitHub returned HTTP {response.status_code}")
        payload = response.json()
        latest_version = str(payload["tag_name"]).removeprefix("v")
        if not latest_version:
            raise ValueError("latest release has an empty tag_name")
    except (requests.RequestException, KeyError, TypeError, ValueError, RuntimeError) as exc:
        return (
            {"status": "error", "installed_version": installed_version, "is_latest": False},
            [AgentMessage("error", "UPDATE_CHECK_FAILED", f"Could not check GitHub releases ({type(exc).__name__}); retry later.")],
        )

    is_latest = installed_version == latest_version
    code = "UP_TO_DATE" if is_latest else "UPDATE_AVAILABLE"
    text = (
        f"Anticharon {installed_version} is the latest GitHub release."
        if is_latest
        else f"Anticharon {latest_version} is available; run the experimental update tool to install it."
    )
    return (
        {
            "status": "success",
            "installed_version": installed_version,
            "latest_version": latest_version,
            "is_latest": is_latest,
            "release_url": payload.get("html_url"),
        },
        [AgentMessage("info", code, text, action=None if is_latest else {"mcp": "run_update(type='install_only')", "cli": "anticharon update --type install_only"})],
    )


def _install_command() -> list[str]:
    """Use uv when present; pip always targets this running interpreter."""
    if shutil.which("uv"):
        return ["uv", "tool", "install", "--force", INSTALL_SOURCE]
    return [sys.executable, "-m", "pip", "install", "--force-reinstall", INSTALL_SOURCE]


def _schedule_parent_termination(install_command: list[str] | None = None) -> None:
    """Let the MCP response flush before terminating this stdio server process."""
    script = (
        "import json, os, signal, subprocess, sys, time; "
        "pid = int(sys.argv[1]); command = json.loads(sys.argv[2]); "
        "time.sleep(0.25); os.kill(pid, signal.SIGTERM); "
        "subprocess.run(command, check=False) if command else None"
    )
    subprocess.Popen(
        [sys.executable, "-c", script, str(os.getpid()), json.dumps(install_command or [])],
        start_new_session=True,
    )


def run_update(update_type: UpdateType | str | int) -> tuple[dict[str, Any], list[AgentMessage]]:
    """Run one experimental update sequence; callers must surface the warning."""
    try:
        selected = parse_update_type(update_type)
    except ValueError:
        return (
            {"status": "error", "type": str(update_type)},
            [AgentMessage("error", "UPDATE_FAILED", "Unknown update type; choose install_only, restart_host, phoenix, phoenix_inverted, or reload_request.")],
        )

    messages = [AgentMessage("warning", "EXPERIMENTAL", "This experimental feature may require manual intervention, for example `hermes gateway restart`.")]
    command = _install_command()

    if selected is UpdateType.PHOENIX_INVERTED:
        _schedule_parent_termination(command)
        messages.append(AgentMessage("warning", "RESTART_REQUIRED", "Anticharon is terminating before reinstalling; the host must respawn the server."))
        return {"status": "success", "type": selected.value, "update_command": command, "restart_scheduled": True}, messages

    completed = subprocess.run(command, capture_output=True, text=True, timeout=120.0, check=False)
    if completed.returncode != 0:
        messages.append(AgentMessage("error", "UPDATE_FAILED", "The reinstall command failed; inspect the host environment and retry."))
        return {"status": "error", "type": selected.value, "update_command": command, "returncode": completed.returncode}, messages

    messages.append(AgentMessage("info", "UPDATE_INSTALLED", "The reinstall command completed successfully."))
    payload: dict[str, Any] = {"status": "success", "type": selected.value, "update_command": command}
    if selected is UpdateType.RESTART_HOST:
        restart = subprocess.run(["hermes", "gateway", "restart"], capture_output=True, text=True, timeout=30.0, check=False)
        payload["host_restart_command"] = ["hermes", "gateway", "restart"]
        if restart.returncode != 0:
            payload["status"] = "error"
            payload["returncode"] = restart.returncode
            messages.append(AgentMessage("error", "UPDATE_FAILED", "Anticharon was reinstalled, but Hermes could not be restarted."))
        else:
            messages.append(AgentMessage("info", "RESTART_REQUIRED", "Hermes restart completed; reconnect the MCP server if your host does not do so automatically."))
    elif selected is UpdateType.PHOENIX:
        _schedule_parent_termination()
        payload["restart_scheduled"] = True
        messages.append(AgentMessage("warning", "RESTART_REQUIRED", "Anticharon is terminating so the host can respawn the updated server."))
    elif selected is UpdateType.RELOAD_REQUEST:
        messages.append(AgentMessage("warning", "RESTART_REQUIRED", "Send `/reload-mcp` in chat to activate the new version; Hermes will ask for confirmation."))
    else:
        messages.append(AgentMessage("warning", "RESTART_REQUIRED", "Restart the MCP host to activate the new version."))
    return payload, messages
