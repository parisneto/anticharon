"""Tests for anticharon.hermes: config detection, stream-grep parsing, and
auto-sync (unaffected by the pricing-engine-v2 rework's pricing math)."""

import json

from anticharon.config import load_config
from anticharon.hermes import (
    extract_models_from_file,
    fetch_models_from_cli,
    get_hermes_models,
    sync_hermes_to_config,
)
from anticharon.tracker import run_tracker

# --- Issue #4 helpers: deterministic Hermes CLI stubs (no real subprocess) ---

# The exact 8-fallback YAML list shape the real Hermes CLI emits for
# `hermes config get fallback_providers` (see Issue #4's reproduction).
HERMES_CLI_YAML_FALLBACKS = """- provider: openrouter
  model: deepseek/deepseek-v4-pro-0813
- provider: openrouter
  model: deepseek/deepseek-v4-flash-0731
- provider: openrouter
  model: qwen/qwen3.7-flash
- provider: openrouter
  model: google/gemini-3.1-flash-lite
- provider: openrouter
  model: minimax/minimax-m2.7
- provider: openrouter
  model: google/gemini-2.5-flash-lite
- provider: openrouter
  model: openai/gpt-4.1-nano
- provider: openrouter
  model: mistralai/mistral-small-3.2
"""

HERMES_CLI_MODEL_BLOCK = """default: openai/gpt-5.6-luna
provider: openrouter
base_url: https://openrouter.ai/api/v1
"""


class _FakeProc:
    def __init__(self, returncode: int = 0, stdout: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _install_cli_stub(monkeypatch, model_out, fallback_out, fallback_rc=0, available=True):
    """Stub `hermes` CLI availability and `subprocess.run` inside anticharon.hermes."""
    monkeypatch.setattr(
        "anticharon.hermes.shutil.which",
        lambda name: "/usr/local/bin/hermes" if (available and name == "hermes") else None,
    )

    def _run(cmd, **kwargs):
        key = cmd[-1]
        if key == "model":
            return _FakeProc(0, model_out)
        if key == "fallback_providers":
            return _FakeProc(fallback_rc, fallback_out)
        return _FakeProc(1, "")

    monkeypatch.setattr("anticharon.hermes.subprocess.run", _run)


def _install_file_tier(monkeypatch, path):
    """Point the file tier at `path` (None => file tier unavailable)."""
    monkeypatch.setattr(
        "anticharon.hermes.resolve_hermes_config_path",
        lambda custom_path=None, prompt_if_missing=False: path,
    )


def _write_complete_hermes_file(tmp_path):
    content = """model:
  default: openai/gpt-5.6-luna
  provider: openrouter
fallback_providers:
  - provider: openrouter
    model: deepseek/deepseek-v4-pro-0813
  - provider: openrouter
    model: qwen/qwen3.7-flash
"""
    p = tmp_path / "hermes_complete.yaml"
    p.write_text(content, encoding="utf-8")
    return p


def test_hermes_stream_grep_inline_json_fallback_providers(tmp_path):
    vm_yaml_content = """model:
  default: openai/gpt-5.6-luna
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
  api_mode: chat_completions
fallback_providers: '[{"provider":"openrouter","model":"deepseek/deepseek-v4-pro-0813"},{"provider":"openrouter","model":"deepseek/deepseek-v4-flash-0731"},{"provider":"openrouter","model":"qwen/qwen3.7-flash"},{"provider":"google/gemini-3.1-flash-lite","provider":"openrouter","model":"google/gemini-3.1-flash-lite"},{"provider":"openrouter","model":"minimax/minimax-m2.7"},{"provider":"openrouter","model":"google/gemini-2.5-flash-lite"},{"provider":"openrouter","model":"openai/gpt-4.1-nano"}]'
"""
    tf_path = tmp_path / "hermes_config.yaml"
    tf_path.write_text(vm_yaml_content, encoding="utf-8")

    parsed = extract_models_from_file(tf_path)
    assert parsed is not None
    assert parsed["default_model"] == "openai/gpt-5.6-luna"
    assert len(parsed["fallback_models"]) >= 6
    assert parsed["all_models"][0] == "openai/gpt-5.6-luna"
    assert "deepseek/deepseek-v4-pro-0813" in parsed["all_models"]
    assert "openai/gpt-4.1-nano" in parsed["all_models"]

    # Shortlist synchronization
    cf_path = tmp_path / "shortlist.json"
    cf_path.write_text(
        '{"shortlist": ["old/model"], "weight_uncached_prompt": 0.23, "weight_cached_prompt": 0.765, "weight_completion": 0.005}',
        encoding="utf-8",
    )
    changed, new_shortlist, _ = sync_hermes_to_config(parsed, config_path=cf_path, dry_run=False)
    assert changed is True
    assert len(new_shortlist) >= 7
    assert new_shortlist[0] == "openai/gpt-5.6-luna"

    # Weights preserved across sync
    cfg = load_config(cf_path)
    assert cfg["weight_uncached_prompt"] == 0.23
    assert cfg["shortlist"] == new_shortlist


def test_hermes_multiline_yaml_mixed_providers(tmp_path):
    yaml_multiline = """model:
  default: openai/gpt-5.6-luna
  provider: openrouter
fallback_providers:
  - provider: openrouter
    model: deepseek/deepseek-v4-pro-0813
  - provider: anthropic
    model: claude-3-opus
  - provider: openrouter
    model: qwen/qwen3.7-flash
"""
    yf_path = tmp_path / "hermes_multi.yaml"
    yf_path.write_text(yaml_multiline, encoding="utf-8")

    parsed_multi = extract_models_from_file(yf_path)
    assert parsed_multi is not None
    assert parsed_multi["default_model"] == "openai/gpt-5.6-luna"
    assert "claude-3-opus" not in parsed_multi["all_models"]
    assert "deepseek/deepseek-v4-pro-0813" in parsed_multi["all_models"]
    assert "qwen/qwen3.7-flash" in parsed_multi["all_models"]
    assert len(parsed_multi["all_models"]) == 3


def test_run_tracker_with_hermes_config_path(tmp_path, monkeypatch):
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    vm_yaml_content = """model:
  default: openai/gpt-5.6-luna
  provider: openrouter
fallback_providers: '[{"provider":"openrouter","model":"deepseek/deepseek-v4-flash-0731"}]'
"""
    tf_path = tmp_path / "hermes_config.yaml"
    tf_path.write_text(vm_yaml_content, encoding="utf-8")

    res = run_tracker(dry_run=True, hermes_config_path=tf_path, history_path=tmp_path / "history.csv")
    assert res.hermes_integration is not None
    assert res.hermes_integration.detected is True
    assert res.hermes_integration.warning is None
    res_dict = res.to_dict()
    assert "hermes_integration" in res_dict
    assert res_dict["hermes_integration"]["detected"] is True
    assert res_dict["hermes_integration"]["warning"] is None


def test_run_tracker_no_hermes_standalone(tmp_path, monkeypatch):
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    res_no = run_tracker(dry_run=True, no_hermes=True, history_path=tmp_path / "history.csv")
    assert res_no.hermes_integration is not None
    assert res_no.hermes_integration.detected is False
    assert res_no.hermes_integration.method == "standalone"


# --- Issue #4: CLI-tier YAML fallback parsing ---

def test_cli_tier_parses_raw_yaml_fallback_list(monkeypatch):
    """Issue #4 root cause: the real Hermes CLI emits a raw YAML list, not JSON.
    All 8 openrouter fallbacks must be recovered, not silently dropped."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, HERMES_CLI_YAML_FALLBACKS)

    res = fetch_models_from_cli()
    assert res is not None
    assert res["detection"] == "complete"
    assert res["default_model"] == "openai/gpt-5.6-luna"
    assert len(res["fallback_models"]) == 8
    assert res["fallback_models"][0] == "deepseek/deepseek-v4-pro-0813"
    assert res["fallback_models"][-1] == "mistralai/mistral-small-3.2"
    assert len(res["all_models"]) == 9
    assert res["all_models"][0] == "openai/gpt-5.6-luna"


def test_cli_tier_yaml_fallback_skips_non_openrouter_providers(monkeypatch):
    _install_cli_stub(
        monkeypatch,
        HERMES_CLI_MODEL_BLOCK,
        "- provider: openrouter\n  model: qwen/qwen3.7-flash\n- provider: anthropic\n  model: claude-3-opus\n",
    )
    res = fetch_models_from_cli()
    assert res is not None
    assert res["detection"] == "complete"
    assert res["all_models"] == ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash"]


def test_cli_tier_inline_json_fallback_still_parses(monkeypatch):
    """Regression guard: the pre-existing JSON form must keep working."""
    _install_cli_stub(
        monkeypatch,
        HERMES_CLI_MODEL_BLOCK,
        '[{"provider":"openrouter","model":"qwen/qwen3.7-flash"},'
        '{"provider":"openrouter","model":"openai/gpt-4.1-nano"}]',
    )
    res = fetch_models_from_cli()
    assert res is not None
    assert res["detection"] == "complete"
    assert res["all_models"] == [
        "openai/gpt-5.6-luna", "qwen/qwen3.7-flash", "openai/gpt-4.1-nano",
    ]


def test_cli_tier_unparseable_non_empty_fallback_is_incomplete(monkeypatch):
    """Non-empty but unreadable fallback output must NOT masquerade as a
    successful default-only detection (Issue #4's destructive path)."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, "<<binary blob / unknown format>>")
    res = fetch_models_from_cli()
    assert res is not None
    assert res["detection"] == "incomplete"
    assert res["all_models"] == ["openai/gpt-5.6-luna"]


def test_cli_tier_empty_fallback_output_is_complete(monkeypatch):
    """A genuinely fallback-less Hermes config is complete, not incomplete."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, "")
    res = fetch_models_from_cli()
    assert res is not None
    assert res["detection"] == "complete"
    assert res["all_models"] == ["openai/gpt-5.6-luna"]


# --- Issue #4: file-tier trailing-item retention ---

def test_file_tier_retains_last_fallback_when_top_level_key_follows(tmp_path):
    """The YAML fallback block closed by a following top-level key (not EOF)
    used to drop its final item."""
    content = """model:
  default: openai/gpt-5.6-luna
  provider: openrouter
fallback_providers:
  - provider: openrouter
    model: deepseek/deepseek-v4-pro-0813
  - provider: openrouter
    model: qwen/qwen3.7-flash
  - provider: openrouter
    model: openai/gpt-4.1-nano
logging:
  level: info
"""
    p = tmp_path / "hermes_trailing.yaml"
    p.write_text(content, encoding="utf-8")

    parsed = extract_models_from_file(p)
    assert parsed is not None
    assert parsed["detection"] == "complete"
    assert parsed["fallback_models"] == [
        "deepseek/deepseek-v4-pro-0813", "qwen/qwen3.7-flash", "openai/gpt-4.1-nano",
    ]
    assert len(parsed["all_models"]) == 4


# --- Issue #4: detection-outcome combination matrix (5 combinations) ---

def test_matrix_1_complete_cli_is_used(monkeypatch, tmp_path):
    """1. Complete CLI result -> use CLI (file tier never consulted)."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, HERMES_CLI_YAML_FALLBACKS)
    _install_file_tier(monkeypatch, _write_complete_hermes_file(tmp_path))

    res = get_hermes_models()
    assert res is not None
    assert res["method"] == "cli"
    assert res["detection"] == "complete"
    assert len(res["all_models"]) == 9

    # Sync is permitted for a complete result (it is authoritative).
    cf = tmp_path / "shortlist.json"
    cf.write_text(json.dumps({"shortlist": ["old/model"]}), encoding="utf-8")
    changed, new_shortlist, _ = sync_hermes_to_config(res, config_path=cf, dry_run=False)
    assert changed is True
    assert len(new_shortlist) == 9


def test_matrix_2_incomplete_cli_then_complete_file(monkeypatch, tmp_path):
    """2. Incomplete CLI + complete file -> file used, sync permitted, NO warning."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, "<<unparseable>>")
    _install_file_tier(monkeypatch, _write_complete_hermes_file(tmp_path))

    res = get_hermes_models()
    assert res is not None
    assert res["method"] == "file_grep"
    assert res["detection"] == "complete"
    assert len(res["all_models"]) == 3

    # A complete file recovery may legitimately shrink an over-long shortlist.
    cf = tmp_path / "shortlist.json"
    cf.write_text(json.dumps({"shortlist": ["a/1", "b/2", "c/3", "d/4", "e/5"]}), encoding="utf-8")
    changed, new_shortlist, _ = sync_hermes_to_config(res, config_path=cf, dry_run=False)
    assert changed is True
    assert new_shortlist == res["all_models"]

    # Full recovery => no incomplete-detection warning anywhere.
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    tracked = run_tracker(dry_run=True, config_path=cf, history_path=tmp_path / "history.csv")
    assert tracked.hermes_integration.detected is True
    assert tracked.hermes_integration.warning is None
    assert tracked.to_dict()["hermes_integration"]["warning"] is None


def test_matrix_3_unavailable_cli_then_complete_file(monkeypatch, tmp_path):
    """3. Unavailable CLI + complete file -> file used, sync permitted, NO warning."""
    _install_cli_stub(monkeypatch, "", "", available=False)
    _install_file_tier(monkeypatch, _write_complete_hermes_file(tmp_path))

    res = get_hermes_models()
    assert res is not None
    assert res["method"] == "file_grep"
    assert res["detection"] == "complete"

    cf = tmp_path / "shortlist.json"
    cf.write_text(json.dumps({"shortlist": ["old/model"]}), encoding="utf-8")
    changed, new_shortlist, _ = sync_hermes_to_config(res, config_path=cf, dry_run=False)
    assert changed is True
    assert new_shortlist == res["all_models"]

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    tracked = run_tracker(dry_run=True, config_path=cf, history_path=tmp_path / "history.csv")
    assert tracked.hermes_integration.warning is None


def test_matrix_4_incomplete_cli_and_unavailable_file_preserves_shortlist(monkeypatch, tmp_path):
    """4. Incomplete CLI + incomplete/unavailable file -> shortlist preserved,
    visible warning in human output AND --json."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, "<<unparseable>>")
    _install_file_tier(monkeypatch, None)

    res = get_hermes_models()
    assert res is not None
    assert res["detection"] == "incomplete"
    assert res["all_models"] == ["openai/gpt-5.6-luna"]

    existing = ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash", "openai/gpt-4.1-nano"]
    cf = tmp_path / "shortlist.json"
    cf.write_text(json.dumps({"shortlist": list(existing)}), encoding="utf-8")

    changed, new_shortlist, _ = sync_hermes_to_config(res, config_path=cf, dry_run=False)
    assert changed is False
    assert new_shortlist == existing
    assert load_config(cf)["shortlist"] == existing

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    tracked = run_tracker(dry_run=True, config_path=cf, history_path=tmp_path / "history.csv")
    assert tracked.hermes_integration.detected is True
    assert tracked.hermes_integration.warning is not None
    assert "incomplete" in tracked.hermes_integration.warning.lower()
    assert tracked.to_dict()["hermes_integration"]["warning"] is not None


def test_matrix_4b_incomplete_cli_and_incomplete_file_preserves_shortlist(monkeypatch, tmp_path):
    """4 (file-incomplete variant): the file tier is itself incomplete."""
    _install_cli_stub(monkeypatch, HERMES_CLI_MODEL_BLOCK, "<<unparseable>>")
    bad_file = tmp_path / "hermes_bad.yaml"
    bad_file.write_text(
        "model:\n  default: openai/gpt-5.6-luna\nfallback_providers: <<unparseable>>\n",
        encoding="utf-8",
    )
    _install_file_tier(monkeypatch, bad_file)

    res = get_hermes_models()
    assert res is not None
    assert res["detection"] == "incomplete"

    existing = ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash", "openai/gpt-4.1-nano"]
    cf = tmp_path / "shortlist.json"
    cf.write_text(json.dumps({"shortlist": list(existing)}), encoding="utf-8")
    changed, _preserved, _ = sync_hermes_to_config(res, config_path=cf, dry_run=False)
    assert changed is False
    assert load_config(cf)["shortlist"] == existing


def test_matrix_5_unavailable_cli_and_unavailable_file_is_standalone(monkeypatch, tmp_path):
    """5. Unavailable CLI + unavailable file -> ordinary no-Hermes standalone
    behavior, existing configuration preserved (not a new warning path)."""
    _install_cli_stub(monkeypatch, "", "", available=False)
    _install_file_tier(monkeypatch, None)

    assert get_hermes_models() is None

    existing = ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash"]
    cf = tmp_path / "shortlist.json"
    cf.write_text(json.dumps({"shortlist": list(existing)}), encoding="utf-8")

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    tracked = run_tracker(dry_run=True, config_path=cf, history_path=tmp_path / "history.csv")
    assert tracked.hermes_integration.detected is False
    assert tracked.hermes_integration.method == "standalone"
    assert "standalone" in tracked.hermes_integration.warning.lower()
    assert load_config(cf)["shortlist"] == existing


# --- Issue #4: `anticharon test` divergence warning ---

class _FakeModelsResponse:
    status_code = 200

    def json(self):
        return {"data": [{"id": "openai/gpt-5.6-luna"}]}


def test_self_test_flags_hermes_shortlist_divergence(monkeypatch, tmp_path, capsys):
    """`anticharon test` must flag a detected-vs-persisted divergence instead of
    reporting an unqualified pass."""
    from anticharon.tester import run_self_test

    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({"shortlist": ["openai/gpt-5.6-luna"]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg_path))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tester.requests.get", lambda *a, **kw: _FakeModelsResponse())
    monkeypatch.setattr(
        "anticharon.tester.get_hermes_models",
        lambda custom_path=None: {
            "source": "cli:hermes",
            "method": "cli",
            "detection": "complete",
            "default_model": "openai/gpt-5.6-luna",
            "fallback_models": ["qwen/qwen3.7-flash"],
            "all_models": ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash"],
        },
    )

    run_self_test(json_mode=True)
    diag = json.loads(capsys.readouterr().out)
    assert diag["hermes_integration"]["shortlist_divergence"] is True
    assert diag["hermes_integration"]["warning"]


def test_self_test_reports_no_divergence_when_shortlist_matches(monkeypatch, tmp_path, capsys):
    from anticharon.tester import run_self_test

    models = ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash"]
    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({"shortlist": list(models)}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg_path))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tester.requests.get", lambda *a, **kw: _FakeModelsResponse())
    monkeypatch.setattr(
        "anticharon.tester.get_hermes_models",
        lambda custom_path=None: {
            "source": "cli:hermes",
            "method": "cli",
            "detection": "complete",
            "default_model": models[0],
            "fallback_models": models[1:],
            "all_models": list(models),
        },
    )

    run_self_test(json_mode=True)
    diag = json.loads(capsys.readouterr().out)
    assert diag["hermes_integration"]["shortlist_divergence"] is False
    assert diag["hermes_integration"]["warning"] is None
