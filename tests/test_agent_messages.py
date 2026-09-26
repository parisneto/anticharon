"""WS-A2A (W1, GitHub #12): unified agent-message contract.

Covers A2A-1 (`AgentMessage`), A2A-2 (envelope on every CLI `--json` and MCP
payload), A2A-3 (`status` -> MCP `isError` / CLI exit code), A2A-4 (one
human renderer), A2A-5/A2A-8 (legacy keys removed, `price_warnings`),
A2A-6 (Hermes divergence outside `test`), A2A-7 (dry-run wording) and the
PO-approved D-1e codes. Deterministic: every network call is patched.
"""

import asyncio
import json
import re
import sys
import time

import pytest

from anticharon import cli
from anticharon.mcp import server, tool_result
from anticharon.models import (
    ERROR_STATUSES,
    AgentMessage,
    build_envelope,
    render_messages,
)

LEGACY_KEYS = {"notice", "hint", "message", "warning", "error", "priceWarnings", "zdr_warning"}
MODELS = ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash"]
CATALOG = {
    m: {"id": m, "canonical_slug": m, "pricing": {"prompt": "0.000001", "completion": "0.000002"}}
    for m in MODELS
}


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _codes(envelope):
    return [m["code"] for m in envelope["messages"]]


def _assert_envelope(envelope):
    """The D-1b envelope: fixed leading keys, messages never empty, ends with COMPLETED."""
    assert list(envelope)[:3] == ["status", "messages", "elapsed_ms"]
    assert envelope["status"] in {"success", "warning", "error", "refused", "not_monitored"}
    assert isinstance(envelope["elapsed_ms"], int) and envelope["elapsed_ms"] >= 0
    assert envelope["messages"], "messages must never be empty"
    assert envelope["messages"][-1]["code"] == "COMPLETED"
    for m in envelope["messages"]:
        assert m["level"] in {"info", "warning", "error"}
        assert m["code"] and m["text"]
    assert not LEGACY_KEYS & set(envelope), f"legacy keys present: {LEGACY_KEYS & set(envelope)}"


@pytest.fixture
def sandbox(monkeypatch, tmp_path):
    """Isolated config/data/home, no Hermes, and a two-model mocked OpenRouter."""
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": list(MODELS)}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: CATALOG)
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})
    for module in ("anticharon.tracker", "anticharon.mcp", "anticharon.cli"):
        monkeypatch.setattr(f"{module}.get_hermes_models", lambda *a, **kw: None)
    return tmp_path


def _hermes(models, detection="complete"):
    return {
        "source": "cli:hermes", "method": "cli", "detection": detection,
        "default_model": models[0], "fallback_models": models[1:], "all_models": list(models),
    }


def _cli_json(monkeypatch, capsys, *argv):
    """Run the real argparse entrypoint; return (exit_code, parsed stdout JSON)."""
    monkeypatch.setattr(sys, "argv", ["anticharon", *argv])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    return exc.value.code, json.loads(capsys.readouterr().out)


# --- A2A-1 / A2A-2: AgentMessage and envelope -------------------------------


def test_agent_message_to_dict_omits_unset_optionals():
    assert AgentMessage("info", "X", "t").to_dict() == {"level": "info", "code": "X", "text": "t"}
    full = AgentMessage("warning", "Y", "t", action={"mcp": "a()", "cli": "b"}, model="m/x").to_dict()
    assert full == {"level": "warning", "code": "Y", "text": "t", "action": {"mcp": "a()", "cli": "b"}, "model": "m/x"}


def test_build_envelope_orders_keys_and_appends_timed_completed():
    started = time.perf_counter() - 0.25
    env = build_envelope({"data": 1, "status": "warning"}, [AgentMessage("warning", "W", "w")], started)
    _assert_envelope(env)
    assert list(env) == ["status", "messages", "elapsed_ms", "data"]
    assert env["status"] == "warning"
    assert _codes(env) == ["W", "COMPLETED"]
    assert env["elapsed_ms"] >= 250
    assert re.fullmatch(r"Anticharon processed your request successfully in \d+\.\ds\.", env["messages"][-1]["text"])


def test_build_envelope_never_empty_and_error_completion_is_not_success():
    env = build_envelope({"status": "success"}, [], time.perf_counter())
    assert _codes(env) == ["COMPLETED"]
    err = build_envelope({"status": "refused"}, [AgentMessage("error", "E", "e")], time.perf_counter())
    assert "successfully" not in err["messages"][-1]["text"]


# --- A2A-3: status -> isError / exit code -----------------------------------


def test_error_statuses_are_exactly_error_and_refused():
    assert ERROR_STATUSES == {"error", "refused"}


@pytest.mark.parametrize("status", ["success", "warning", "not_monitored"])
def test_tool_result_passes_normal_statuses_through(status):
    env = build_envelope({"status": status}, [], time.perf_counter())
    assert tool_result(env) is env


@pytest.mark.parametrize("status", ["error", "refused"])
def test_tool_result_maps_error_statuses_to_is_error_with_same_body(status):
    """Through the real SDK call path: isError: true and the same JSON body."""
    from mcp.server.mcpserver import MCPServer

    probe = MCPServer("probe")
    env = build_envelope({"status": status, "k": 1}, [AgentMessage("error", "E", "e")], time.perf_counter())

    @probe.tool(name="probe")
    def _probe() -> dict:
        return tool_result(env)

    res = _run_async(probe.call_tool("probe", {}))
    assert res.is_error is True
    assert json.loads(res.content[0].text) == env
    assert res.structured_content == env


@pytest.mark.parametrize("status,code", [("success", 0), ("warning", 0), ("not_monitored", 0), ("error", 1), ("refused", 1)])
def test_cli_exit_code_follows_status(status, code):
    assert cli._exit_code(status) == code


# --- A2A-2 / A2A-5: every MCP tool returns the envelope ---------------------

MCP_CALLS = {
    "check_prices": {},
    "run_prices": {"dry_run": True},
    "get_model_history": {"format": "json"},
    "discover_models": {"query": "gpt"},
    "import_hermes_models": {},
    "add_model": {"model_id": MODELS[0]},
    "remove_model": {"model_id": MODELS[1]},
    "list_models": {},
    "self_test": {},
    "calibrate_token_weights": {"csv_path": "docs/sample/openrouter_activity_2026-08-24.csv"},
    "calibrate_fast": {"weight_uncached_prompt": 0.5, "weight_cached_prompt": 0.4, "weight_completion": 0.1, "dry_run": True},
    "check_updates": {},
    "run_update": {"type": "install_only"},
}


def test_every_registered_mcp_tool_returns_the_envelope(sandbox, monkeypatch, capsys):
    monkeypatch.setattr("anticharon.mcp.fetch_catalog", lambda **kw: [])
    monkeypatch.setattr("anticharon.tester.run_self_test", lambda **kw: True)
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda timeout=10.0: CATALOG)
    monkeypatch.setattr("anticharon.mcp.check_for_updates", lambda version: ({"status": "success", "installed_version": version, "latest_version": version, "is_latest": True}, []))
    monkeypatch.setattr("anticharon.mcp.execute_update", lambda update_type: ({"status": "success", "type": str(update_type)}, []))
    tools = {t.name for t in _run_async(server.list_tools())}
    assert tools == set(MCP_CALLS), "new MCP tool: add it to MCP_CALLS so its envelope is tested"
    for name, args in MCP_CALLS.items():
        res = _run_async(server.call_tool(name, args))
        assert res.is_error is False, name
        _assert_envelope(json.loads(res.content[0].text))
    csv_env = json.loads(_run_async(server.call_tool("get_model_history", {"format": "csv"})).content[0].text)
    _assert_envelope(csv_env)
    # ADR 0001 stdio isolation: tool calls print nothing to stdout.
    assert capsys.readouterr().out == ""


def test_check_prices_payload_uses_price_warnings_and_marks_preview(sandbox):
    """`check_prices` is a local-only read (D-19): with nothing persisted yet,
    it reports DATA_STALE (no run has ever populated history.csv/alerts.json)
    rather than PREVIEW_ONLY (that code is for a `dry_run` write tool, and
    check_prices never writes at all)."""
    env = json.loads(_run_async(server.call_tool("check_prices", {})).content[0].text)
    assert "price_warnings" in env and "priceWarnings" not in env
    assert "DATA_STALE" in _codes(env)
    assert "HERMES_NOT_DETECTED" in _codes(env)
    assert env["status"] == "success"  # standalone stays successful (D-1e)


def test_run_prices_marks_preview_and_check_prices_reads_it_back(sandbox):
    """`run_prices(dry_run=True)` computes without persisting (PREVIEW_ONLY);
    `run_prices(dry_run=False)` persists, and a subsequent `check_prices`
    local read reflects it with no DATA_STALE/PREVIEW_ONLY message (D-18/D-19)."""
    preview = json.loads(_run_async(server.call_tool("run_prices", {"dry_run": True})).content[0].text)
    assert "PREVIEW_ONLY" in _codes(preview)
    still_stale = json.loads(_run_async(server.call_tool("check_prices", {})).content[0].text)
    assert "DATA_STALE" in _codes(still_stale)

    saved = json.loads(_run_async(server.call_tool("run_prices", {"dry_run": False})).content[0].text)
    assert "PREVIEW_ONLY" not in _codes(saved)
    fresh = json.loads(_run_async(server.call_tool("check_prices", {})).content[0].text)
    assert "DATA_STALE" not in _codes(fresh)
    assert fresh["prices_shortlist"]


def test_import_hermes_models_without_hermes_is_a_warning_not_an_error(sandbox):
    res = _run_async(server.call_tool("import_hermes_models", {}))
    env = json.loads(res.content[0].text)
    assert res.is_error is False
    assert env["status"] == "warning" and env["detected"] is False
    not_detected = [m for m in env["messages"] if m["code"] == "HERMES_NOT_DETECTED"]
    assert len(not_detected) == 1 and not_detected[0]["level"] == "warning"
    assert set(not_detected[0]["action"]) == {"mcp", "cli"}


# --- A2A-2 / A2A-3: every CLI --json output ---------------------------------


@pytest.mark.parametrize("argv", [
    ("run", "--json", "--no-hermes", "--dry-run"),
    ("check", "--json", "--no-hermes"),
    ("history", "--json", "--no-hermes"),
    ("info", "--json"),
    ("model", "list", "--json"),
    ("model", "add", "x/new-model", "--dry-run", "--json"),
    ("model", "remove", MODELS[1], "--dry-run", "--json"),
    ("model", "discover", "--json"),
    ("model", "sync", "--json"),
])
def test_cli_json_outputs_carry_the_envelope_and_exit_zero(sandbox, monkeypatch, capsys, argv):
    monkeypatch.setattr("anticharon.cli.fetch_catalog", lambda **kw: [])
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kw: {"x/new-model": {}})
    code, env = _cli_json(monkeypatch, capsys, *argv)
    assert code == 0
    _assert_envelope(env)


def test_cli_test_json_carries_envelope(sandbox, monkeypatch, capsys):
    class _Ok:
        status_code = 200

        def json(self):
            return {"data": []}

    monkeypatch.setattr("anticharon.tester.requests.get", lambda *a, **kw: _Ok())
    code, env = _cli_json(monkeypatch, capsys, "test", "--json", "--no-hermes")
    assert code == 0
    _assert_envelope(env)
    assert env["status"] == "success" and env["all_passed"] is True


def test_self_test_failure_is_status_error_with_self_test_failed(sandbox, monkeypatch, capsys):
    from anticharon.tester import run_self_test

    monkeypatch.setattr("anticharon.tester.requests.get", lambda *a, **kw: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr("anticharon.tester.calculate_effective_cost", lambda **kw: 0.0)
    assert run_self_test(no_hermes=True, json_mode=True) is False
    env = json.loads(capsys.readouterr().out)
    _assert_envelope(env)
    assert env["status"] == "error"
    assert "SELF_TEST_FAILED" in _codes(env)
    assert env["math_engine"]["error"]  # per-check error stays as diagnostic data (D-1c)


def test_model_remove_absent_is_error_exit_one(sandbox, monkeypatch, capsys):
    code, env = _cli_json(monkeypatch, capsys, "model", "remove", "not/there", "--json")
    assert code == 1
    _assert_envelope(env)
    assert env["status"] == "error"
    assert env["messages"][0] == {
        "level": "error", "code": "SHORTLIST_UNCHANGED",
        "text": "Model 'not/there' is not in the shortlist; nothing was removed.",
        "action": {"mcp": "read resource anticharon://shortlist.json", "cli": "anticharon model list"},
        "model": "not/there",
    }


def test_model_add_reports_persisted_vs_preview(sandbox, monkeypatch, capsys):
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kw: {"x/new": {}})
    _, preview = _cli_json(monkeypatch, capsys, "model", "add", "x/new", "--dry-run", "--json")
    assert "PREVIEW_ONLY" in _codes(preview)
    _, saved = _cli_json(monkeypatch, capsys, "model", "add", "x/new", "--json")
    assert "SHORTLIST_UPDATED" in _codes(saved) and "PREVIEW_ONLY" not in _codes(saved)
    _, dup = _cli_json(monkeypatch, capsys, "model", "add", "x/new", "--json")
    assert dup["status"] == "warning" and _codes(dup)[0] == "SHORTLIST_UNCHANGED"


def test_model_add_unknown_slug_emits_no_exact_match(sandbox, monkeypatch, capsys):
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda timeout=5.0: CATALOG)
    _, env = _cli_json(monkeypatch, capsys, "model", "add", "fake/slug", "--dry-run", "--json")
    no_match = [m for m in env["messages"] if m["code"] == "NO_EXACT_MATCH"]
    assert len(no_match) == 1
    assert no_match[0]["model"] == "fake/slug"
    assert no_match[0]["action"]["mcp"] == 'discover_models(query="fake/slug")'


def test_cli_model_sync_without_hermes_is_warning_exit_zero(sandbox, monkeypatch, capsys):
    """D-1e: absence of the optional Hermes config is never an error (was exit 1)."""
    code, env = _cli_json(monkeypatch, capsys, "model", "sync", "--json")
    assert code == 0
    assert env["status"] == "warning" and env["detected"] is False
    assert _codes(env) == ["HERMES_NOT_DETECTED", "COMPLETED"]


def test_cli_sync_and_mcp_import_return_the_same_payload(sandbox, monkeypatch, capsys):
    hermes = _hermes(list(reversed(MODELS)))
    monkeypatch.setattr("anticharon.cli.get_hermes_models", lambda *a, **kw: hermes)
    monkeypatch.setattr("anticharon.mcp.get_hermes_models", lambda *a, **kw: hermes)
    _, cli_env = _cli_json(monkeypatch, capsys, "model", "sync", "--dry-run", "--json")
    mcp_env = json.loads(_run_async(server.call_tool("import_hermes_models", {"dry_run": True})).content[0].text)
    strip = lambda e: {k: v for k, v in e.items() if k not in ("elapsed_ms", "messages")}
    assert strip(cli_env) == strip(mcp_env)
    assert _codes(cli_env)[:-1] == _codes(mcp_env)[:-1] == ["PREVIEW_ONLY"]


# --- D-1e: CALIBRATION_INPUT_INVALID and ZDR_LIVE_LIMITED -------------------


def test_calibrate_invalid_input_returns_error_envelope_exit_one(sandbox, monkeypatch, capsys):
    code, env = _cli_json(monkeypatch, capsys, "calibrate", str(sandbox / "missing.csv"), "--json")
    assert code == 1
    _assert_envelope(env)
    assert env["status"] == "error"
    assert env["messages"][0]["code"] == "CALIBRATION_INPUT_INVALID"
    assert env["messages"][0]["level"] == "error"
    assert str(sandbox) not in json.dumps(env)  # safe text: no host path echoed


def test_calibrate_json_is_pure_json_and_persists(sandbox, sample_dir, monkeypatch, capsys):
    """Regression: `calibrate --json` used to print a non-JSON 'saved' line after the JSON."""
    csv_path = sample_dir / "openrouter_activity_2026-08-24.csv"
    code, env = _cli_json(monkeypatch, capsys, "calibrate", str(csv_path), "--json")
    assert code == 0
    _assert_envelope(env)
    assert "SHORTLIST_UPDATED" in _codes(env)
    saved = json.loads((sandbox / "shortlist.json").read_text(encoding="utf-8"))
    assert saved["weight_completion"] == env["weight_completion"]


def test_calibrate_internal_failure_is_not_reported_as_invalid_input(sandbox, monkeypatch, capsys):
    def boom(path):
        raise RuntimeError("bug")

    monkeypatch.setattr("anticharon.cli.parse_activity_log", boom)
    monkeypatch.setattr(sys, "argv", ["anticharon", "calibrate", "x.csv", "--json"])
    with pytest.raises(RuntimeError):
        cli.main()
    assert "CALIBRATION_INPUT_INVALID" not in capsys.readouterr().out


def test_discover_zdr_cap_is_a_zdr_live_limited_message(sandbox, monkeypatch, capsys):
    from anticharon.discovery import CatalogModel

    many = [CatalogModel(id=f"p/m{i}", name=f"m{i}", context_length=1, prompt_price_1m=1.0,
                         completion_price_1m=1.0, blended_price_1m=1.0 + i, is_promo=False, output_modalities=["text"],
                         canonical_slug=f"p/m{i}") for i in range(3)]
    monkeypatch.setattr("anticharon.cli.fetch_catalog", lambda **kw: many)
    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing",
                        lambda *a, **kw: [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}])
    (sandbox / "shortlist.json").write_text(json.dumps({"shortlist": [], "max_zdr_check_count": 1}), encoding="utf-8")
    _, env = _cli_json(monkeypatch, capsys, "model", "discover", "--zdr", "--json")
    limited = [m for m in env["messages"] if m["code"] == "ZDR_LIVE_LIMITED"]
    assert len(limited) == 1 and limited[0]["level"] == "warning"
    assert "1 of 3" in limited[0]["text"] and "limited" in limited[0]["text"]
    assert "zdr_warning" not in env


# --- A2A-6: HERMES_DIVERGENT on run/check -----------------------------------


def test_check_emits_order_sensitive_hermes_divergent(sandbox, monkeypatch, capsys):
    """Same models, different order: Hermes fallback order matters (D-5)."""
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda *a, **kw: _hermes(list(reversed(MODELS))))
    _, env = _cli_json(monkeypatch, capsys, "check", "--json")
    divergent = [m for m in env["messages"] if m["code"] == "HERMES_DIVERGENT"]
    assert len(divergent) == 1 and divergent[0]["level"] == "warning"
    assert divergent[0]["action"]["mcp"] == "import_hermes_models(dry_run=false)"


def test_check_without_divergence_emits_no_hermes_warning(sandbox, monkeypatch, capsys):
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda *a, **kw: _hermes(MODELS))
    _, env = _cli_json(monkeypatch, capsys, "check", "--json")
    assert not [c for c in _codes(env) if c.startswith("HERMES_")]


def test_divergence_check_is_shared_with_self_test(monkeypatch):
    from anticharon import hermes, tester

    assert tester.hermes_shortlist_divergent is hermes.hermes_shortlist_divergent
    assert tester.hermes_detection_messages is hermes.hermes_detection_messages
    assert hermes.hermes_shortlist_divergent(["a", "b"], ["b", "a"]) is True
    assert hermes.hermes_shortlist_divergent(["a", "b"], ["a", "b"]) is False


# --- A2A-7: dry-run wording --------------------------------------------------


def test_run_persisting_hermes_sync_reports_shortlist_updated_then_unchanged(sandbox, monkeypatch, capsys):
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda *a, **kw: _hermes(list(reversed(MODELS))))
    _, first = _cli_json(monkeypatch, capsys, "run", "--json")
    assert "SHORTLIST_UPDATED" in _codes(first)
    assert "PREVIEW_ONLY" not in _codes(first) and "HERMES_DIVERGENT" not in _codes(first)
    _, second = _cli_json(monkeypatch, capsys, "run", "--json")
    assert "SHORTLIST_UNCHANGED" in _codes(second)


def test_check_human_output_says_detected_not_synced_and_renders_messages(sandbox, monkeypatch, capsys):
    """F-17: a dry run must not claim Hermes was 'Synced'; human output shows the JSON messages."""
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda *a, **kw: _hermes(list(reversed(MODELS))))
    _, env = _cli_json(monkeypatch, capsys, "check", "--json")
    monkeypatch.setattr(sys, "argv", ["anticharon", "check"])
    with pytest.raises(SystemExit):
        cli.main()
    out = capsys.readouterr().out
    assert "Synced" not in out
    assert "Hermes:    Detected" in out
    for code in _codes(env):
        assert f"[{code}]" in out


def test_api_fallback_message_when_openrouter_unreachable(sandbox, monkeypatch, capsys):
    """API_FALLBACK can only come from `run` (D-19): `check` never calls
    OpenRouter at all, so it cannot observe an API failure directly."""
    _cli_json(monkeypatch, capsys, "run", "--json", "--no-hermes")  # seed history.csv
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    _, env = _cli_json(monkeypatch, capsys, "run", "--json", "--no-hermes")
    assert env["api_offline_fallback"] is True
    assert _codes(env)[0] == "API_FALLBACK"


# --- A2A-4: renderer ---------------------------------------------------------


def test_render_messages_prints_code_text_and_cli_action(capsys):
    env = build_envelope(
        {"status": "success"},
        [AgentMessage("warning", "HERMES_DIVERGENT", "differs", action={"mcp": "m()", "cli": "anticharon model sync"})],
        time.perf_counter(),
    )
    render_messages(env["messages"])
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "⚠️  [HERMES_DIVERGENT] differs"
    assert out[1] == "     ↳ anticharon model sync"
    assert out[2].startswith("ℹ️  [COMPLETED] ")


# --- Acceptance (ledger §6 WS-A2A): every emitted code is documented ---------


def test_every_emitted_code_is_documented_in_llms_txt_and_spec():
    from pathlib import Path

    root = Path(__file__).parent.parent
    source = "\n".join(p.read_text(encoding="utf-8") for p in (root / "src" / "anticharon").glob("*.py"))
    codes = set(re.findall(r'AgentMessage\(\s*(?:level=)?"\w+",\s*(?:code=)?"([A-Z_]+)"', source))
    assert {"COMPLETED", "PREVIEW_ONLY", "HERMES_DIVERGENT", "ZDR_LIVE_LIMITED"} <= codes  # regex sanity
    llms = (root / "llms.txt").read_text(encoding="utf-8")
    spec = (root / "docs" / "specs" / "spec_v1_anticharon.md").read_text(encoding="utf-8")
    spec_10 = spec[spec.index("## 10. Model Context Protocol"):]
    for code in sorted(codes):
        assert f"`{code}`" in llms, f"{code} missing from llms.txt"
        assert f"`{code}`" in spec_10, f"{code} missing from spec §10"
    from anticharon.mcp import resource_llms_txt

    assert not (root / "src" / "anticharon" / "llms.txt").exists()
    assert resource_llms_txt() == llms.strip()
