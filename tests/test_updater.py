"""Deterministic coverage for W5 self-update operations."""

import argparse
import json
from pathlib import Path

import pytest

from anticharon import mcp
from anticharon.cli import cmd_check_updates, cmd_update
from anticharon.updater import UpdateType, check_updates, run_update

LATEST_RELEASE_FIXTURE = Path(__file__).parent / "fixtures" / "github_releases_latest.json"


class _Response:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or json.loads(LATEST_RELEASE_FIXTURE.read_text(encoding="utf-8"))

    def json(self):
        return self._payload


class _Process:
    def __init__(self, returncode=0):
        self.returncode = returncode


def _read(result):
    if hasattr(result, "content"):
        return json.loads(result.content[0].text)
    return result


def test_check_updates_reports_is_latest_with_two_second_timeout(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen.update(url=url, headers=headers, timeout=timeout)
        return _Response(payload=json.loads(LATEST_RELEASE_FIXTURE.read_text(encoding="utf-8")))

    monkeypatch.setattr("anticharon.updater.requests.get", fake_get)
    payload, messages = check_updates("0.5.5")

    assert payload["is_latest"] is True
    assert messages[0].code == "UP_TO_DATE"
    assert seen["timeout"] == 2.0
    assert payload["release_url"] == "https://github.com/parisneto/anticharon/releases/tag/v0.5.5"


def test_check_updates_ahead_of_latest_reports_is_latest_true(monkeypatch):
    monkeypatch.setattr(
        "anticharon.updater.requests.get",
        lambda *args, **kwargs: _Response(payload=json.loads(LATEST_RELEASE_FIXTURE.read_text(encoding="utf-8"))),
    )
    payload, messages = check_updates("0.6.0")

    assert payload["is_latest"] is True
    assert payload["latest_version"] == "0.5.5"
    assert messages[0].code == "UP_TO_DATE"
    assert "ahead of the latest GitHub release" in messages[0].text
    assert messages[0].action is None


def test_check_updates_behind_latest_reports_update_available(monkeypatch):
    monkeypatch.setattr(
        "anticharon.updater.requests.get",
        lambda *args, **kwargs: _Response(payload=json.loads(LATEST_RELEASE_FIXTURE.read_text(encoding="utf-8"))),
    )
    payload, messages = check_updates("0.5.4")

    assert payload["is_latest"] is False
    assert payload["latest_version"] == "0.5.5"
    assert messages[0].code == "UPDATE_AVAILABLE"
    assert messages[0].action is not None



def test_check_updates_failure_is_an_error_and_mcp_is_error(monkeypatch):
    import requests

    def unavailable(*args, **kwargs):
        raise requests.Timeout("offline")

    monkeypatch.setattr("anticharon.updater.requests.get", unavailable)

    payload, messages = check_updates("0.5.5")
    result = mcp.check_updates()

    assert payload["status"] == "error"
    assert payload["is_latest"] is False
    assert messages[0].code == "UPDATE_CHECK_FAILED"
    assert result.is_error is True
    assert _read(result)["messages"][0]["code"] == "UPDATE_CHECK_FAILED"


def test_run_update_uses_running_interpreter_pip_fallback_and_experimental_warning(monkeypatch):
    commands = []
    monkeypatch.setattr("anticharon.updater.shutil.which", lambda name: None)
    monkeypatch.setattr("anticharon.updater.subprocess.run", lambda command, **kwargs: commands.append((command, kwargs)) or _Process())

    payload, messages = run_update("install_only")

    assert payload["status"] == "success"
    assert commands[0][0][:4] == [__import__("sys").executable, "-m", "pip", "install"]
    assert commands[0][0][4] == "--force-reinstall"
    assert [message.code for message in messages] == ["EXPERIMENTAL", "UPDATE_INSTALLED", "RESTART_REQUIRED"]


def test_run_update_invalid_type_still_returns_experimental_warning():
    payload, messages = run_update("not-a-type")

    assert payload["status"] == "error"
    assert [message.code for message in messages] == ["EXPERIMENTAL", "UPDATE_FAILED"]


def test_run_update_restart_host_runs_named_host_command(monkeypatch):
    commands = []
    monkeypatch.setattr("anticharon.updater.shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("anticharon.updater.subprocess.run", lambda command, **kwargs: commands.append(command) or _Process())

    payload, messages = run_update(UpdateType.RESTART_HOST)

    assert commands == [
        ["uv", "tool", "install", "--force", "git+https://github.com/parisneto/anticharon.git"],
        ["hermes", "gateway", "restart"],
    ]
    assert payload["host_restart_command"] == ["hermes", "gateway", "restart"]
    assert messages[0].code == "EXPERIMENTAL"


def test_run_update_phoenix_sequences_are_mocked_and_named(monkeypatch):
    scheduled = []
    monkeypatch.setattr("anticharon.updater.shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("anticharon.updater.subprocess.run", lambda *args, **kwargs: _Process())
    monkeypatch.setattr("anticharon.updater._schedule_parent_termination", lambda command=None: scheduled.append(command))

    phoenix, _ = run_update("phoenix")
    reload, _ = run_update("4")

    assert phoenix["type"] == "phoenix"
    assert phoenix["restart_scheduled"] is True
    assert scheduled == [None]
    assert reload["type"] == "reload_request"
    assert "restart_scheduled" not in reload


def test_cli_update_commands_preserve_envelope_parity(monkeypatch, capsys):
    monkeypatch.setattr("anticharon.cli.check_for_updates", lambda version: ({"status": "success", "installed_version": version, "latest_version": version, "is_latest": True}, []))
    monkeypatch.setattr("anticharon.cli.execute_update", lambda update_type: ({"status": "success", "type": str(update_type)}, []))

    assert cmd_check_updates(argparse.Namespace(json=True)) == 0
    assert json.loads(capsys.readouterr().out)["is_latest"] is True
    assert cmd_update(argparse.Namespace(type="reload_request", json=True)) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "reload_request"


def test_install_only_tells_hermes_and_other_hosts_how_to_activate_the_new_version(monkeypatch):
    monkeypatch.setattr("anticharon.updater.shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("anticharon.updater.subprocess.run", lambda command, **kwargs: _Process())

    _, messages = run_update("install_only")

    text = next(m.text for m in messages if m.code == "RESTART_REQUIRED")
    assert "/reload-mcp" in text and "Hermes" in text
    assert "restart" in text and "reconnect" in text  # generic hosts
    assert "check_updates" in text  # the stale version report is called out


def test_the_mcp_update_tool_advertises_only_install_only_and_marks_the_rest_deprecated():
    import asyncio

    from anticharon.mcp import server

    tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "run_update")
    description = tool.description
    assert "install_only" in description and "/reload-mcp" in description
    assert "restart or reconnect" in description.replace("restart the host or reconnect", "restart or reconnect") or "reconnect the MCP server" in description
    assert "Deprecated" in description and "0.8.0" in description
    for deprecated in ("restart_host", "phoenix", "reload_request"):
        assert f"- {deprecated}:" not in description  # no longer presented as options


def test_update_reports_the_version_it_replaced_and_that_the_default_branch_may_be_older(monkeypatch):
    from anticharon import __version__

    monkeypatch.setattr("anticharon.updater.shutil.which", lambda name: "/usr/bin/uv")
    monkeypatch.setattr("anticharon.updater.subprocess.run", lambda command, **kwargs: _Process())

    payload, messages = run_update("install_only")

    assert payload["installed_before"] == __version__
    text = next(m.text for m in messages if m.code == "RESTART_REQUIRED")
    assert "older version" in text and __version__ in text


def test_deprecated_update_types_are_accepted_but_not_listed_in_cli_help_or_the_mcp_schema(capsys):
    import asyncio

    from anticharon.cli import build_parser
    from anticharon.mcp import server

    parser, _, _ = build_parser()
    for value in ("install_only", "1", "2", "phoenix", "reload_request"):
        assert parser.parse_args(["update", "--type", value]).type in {"install_only", "restart_host", "phoenix", "reload_request"}
    with pytest.raises(SystemExit):
        parser.parse_args(["update", "--type", "bogus"])
    capsys.readouterr()
    with pytest.raises(SystemExit):
        parser.parse_args(["update", "-h"])
    help_text = capsys.readouterr().out
    for hidden in ("restart_host", "phoenix", "reload_request", "{1,2,3,4"):
        assert hidden not in help_text

    tool = next(t for t in asyncio.run(server.list_tools()) if t.name == "run_update")
    schema = json.dumps(tool.input_schema)
    for hidden in ("restart_host", "phoenix", "reload_request", "enum"):
        assert hidden not in schema
    assert tool.input_schema["properties"]["type"]["default"] == "install_only"
