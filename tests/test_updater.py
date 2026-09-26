"""Deterministic coverage for W5 self-update operations."""

import argparse
import json
from pathlib import Path

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
    inverted, _ = run_update("4")

    assert phoenix["type"] == "phoenix"
    assert phoenix["restart_scheduled"] is True
    assert scheduled[0] is None
    assert inverted["type"] == "phoenix_inverted"
    assert inverted["restart_scheduled"] is True
    assert scheduled[1] == ["uv", "tool", "install", "--force", "git+https://github.com/parisneto/anticharon.git"]


def test_cli_update_commands_preserve_envelope_parity(monkeypatch, capsys):
    monkeypatch.setattr("anticharon.cli.check_for_updates", lambda version: ({"status": "success", "installed_version": version, "latest_version": version, "is_latest": True}, []))
    monkeypatch.setattr("anticharon.cli.execute_update", lambda update_type: ({"status": "success", "type": str(update_type)}, []))

    assert cmd_check_updates(argparse.Namespace(json=True)) == 0
    assert json.loads(capsys.readouterr().out)["is_latest"] is True
    assert cmd_update(argparse.Namespace(type="reload_request", json=True)) == 0
    assert json.loads(capsys.readouterr().out)["type"] == "reload_request"
