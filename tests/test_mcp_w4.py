"""Deterministic coverage for W4 MCP tools, calibration, and resources."""

import asyncio
import json

from anticharon import mcp


def _read(result):
    if hasattr(result, "content"):
        return json.loads(result.content[0].text)
    return result


def test_calibrate_fast_normalizes_and_backs_up_config(tmp_path, monkeypatch):
    config = tmp_path / "shortlist.json"
    original = '{"shortlist": ["p/model"], "weight_uncached_prompt": 0.5}\n'
    config.write_text(original, encoding="utf-8")
    monkeypatch.setattr(mcp, "get_config_path", lambda: config)

    result = mcp.calibrate_fast(0.5000002, 0.3999999, 0.1)

    assert result["status"] == "success"
    assert result["weight_uncached_prompt"] == 0.5
    assert result["weight_cached_prompt"] == 0.4
    assert result["weight_completion"] == 0.1
    assert config.with_name("shortlist.json.bak").read_text(encoding="utf-8") == original
    assert any(message["code"] == "CALIBRATION_BACKUP" for message in result["messages"])


def test_calibrate_fast_rejects_out_of_tolerance_sum_without_mutation(tmp_path, monkeypatch):
    config = tmp_path / "shortlist.json"
    original = '{"sentinel": true}'
    config.write_text(original, encoding="utf-8")
    monkeypatch.setattr(mcp, "get_config_path", lambda: config)

    result = _read(mcp.calibrate_fast(0.5, 0.4, 0.100002))

    assert result["status"] == "error"
    assert config.read_text(encoding="utf-8") == original
    assert not config.with_name("shortlist.json.bak").exists()


def test_calibrate_token_weights_uses_local_csv_and_backup(tmp_path, monkeypatch):
    config = tmp_path / "shortlist.json"
    config.write_text('{"weight_completion": 0.2}', encoding="utf-8")
    csv_path = tmp_path / "activity.csv"
    csv_path.write_text("tokens_prompt,tokens_cached,tokens_completion\n1000,600,100\n", encoding="utf-8")
    monkeypatch.setattr(mcp, "get_config_path", lambda: config)

    result = _read(mcp.calibrate_token_weights(str(csv_path)))

    assert result["status"] == "success"
    assert result["weight_uncached_prompt"] == 0.363636
    assert result["weight_cached_prompt"] == 0.545455
    assert result["weight_completion"] == 0.090909
    assert config.with_name("shortlist.json.bak").read_text(encoding="utf-8") == '{"weight_completion": 0.2}'


def test_calibration_details_resource_is_registered_and_actionable():
    resources = asyncio.run(mcp.server.list_resources())
    assert "anticharon://calibration-details" in {item.uri for item in resources}
    details = mcp.resource_calibration_details()
    assert "calibrate_fast" in details
    assert "anticharon calibrate <csv-path>" in details


def test_import_hermes_tool_defaults_to_persist(monkeypatch):
    monkeypatch.setattr(mcp, "get_hermes_models", lambda **kwargs: {"detected": False})
    seen = {}

    def build(info, config_path=None, dry_run=False):
        seen["dry_run"] = dry_run
        return {"status": "warning", "dry_run": dry_run}, []

    monkeypatch.setattr(mcp, "build_hermes_import_payload", build)
    result = mcp.import_hermes_models()
    assert seen["dry_run"] is False
    assert result["dry_run"] is False


def test_add_model_catalog_unavailable_does_not_persist(tmp_path, monkeypatch):
    from anticharon import manager

    config = tmp_path / "shortlist.json"
    original = '{"shortlist": [{"model": "p/existing", "source": "manual"}]}'
    config.write_text(original, encoding="utf-8")
    monkeypatch.setattr(manager, "get_config_path", lambda: config)
    monkeypatch.setattr(manager, "get_hermes_models", lambda **kwargs: None)
    monkeypatch.setattr(manager, "fetch_openrouter_models", lambda timeout: {})

    result = _read(mcp.add_model("p/new"))

    assert result["status"] == "error"
    assert any(message["code"] == "CATALOG_UNAVAILABLE" for message in result["messages"])
    assert config.read_text(encoding="utf-8") == original


def test_cli_prompt_registry_lists_and_renders(capsys, monkeypatch):
    import sys

    from anticharon.cli import main

    monkeypatch.setattr(sys, "argv", ["anticharon", "prompt"])
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    listing = capsys.readouterr().out
    assert "cost_spike_triage" in listing
    assert "budget_optimization_audit" in listing

    monkeypatch.setattr(sys, "argv", ["anticharon", "prompt", "family_upgrade_discover", "--arg", "model_or_family=qwen"])
    try:
        main()
    except SystemExit as exc:
        assert exc.code == 0
    assert "family 'qwen'" in capsys.readouterr().out


def test_self_test_wraps_json_diagnostics_without_stdout(monkeypatch, capsys):
    from anticharon import tester

    report = {"status": "error", "python": {"supported": False}, "all_passed": False,
              "messages": [{"level": "error", "code": "SELF_TEST_FAILED", "text": "failure details"}]}
    called = {}

    def fake_run_self_test(**kwargs):
        called.update(kwargs)
        print(json.dumps(report))
        return False

    monkeypatch.setattr(tester, "run_self_test", fake_run_self_test)

    result = mcp.self_test()

    assert result.is_error is True
    payload = _read(result)
    assert payload["python"] == {"supported": False}
    assert payload["messages"][0]["code"] == "SELF_TEST_FAILED"
    assert called.get("no_hermes", False) is False
    assert called["json_mode"] is True
    assert capsys.readouterr().out == ""
