"""Tests for anticharon.hermes: config detection, stream-grep parsing, and
auto-sync (unaffected by the pricing-engine-v2 rework's pricing math)."""


from anticharon.config import load_config
from anticharon.hermes import extract_models_from_file, sync_hermes_to_config
from anticharon.tracker import run_tracker


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
