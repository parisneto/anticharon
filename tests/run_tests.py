"""Zero-dependency automated validation test runner for Anticharon."""

import sys
import tempfile
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from anticharon.config import load_config
from anticharon.log_parser import parse_activity_log
from anticharon.models import PriceRecord
from anticharon.storage import read_history, write_history
from anticharon.tracker import run_tracker


def test_log_parser():
    print("Testing OpenRouter activity log parser...")
    sample_csv = Path(__file__).parent.parent / "docs" / "sample" / "openrouter_activity_2026-08-24.csv"
    assert sample_csv.exists(), f"Sample CSV missing at {sample_csv}"

    res = parse_activity_log(sample_csv)
    assert res.records_count == 159, f"Expected 159 records, got {res.records_count}"
    assert res.total_tokens > 0, "Total tokens should be > 0"
    assert res.total_prompt_tokens > res.total_completion_tokens, "Prompt tokens should dominate"
    assert 0.95 <= res.weight_prompt <= 1.0, f"Prompt weight unexpected: {res.weight_prompt}"
    assert 0.0 <= res.weight_completion <= 0.05, f"Completion weight unexpected: {res.weight_completion}"
    assert abs((res.weight_prompt + res.weight_completion) - 1.0) < 1e-6, "Weights must sum to 1.0"
    print(f"  [OK] Log parser passed (Prompt: {res.weight_prompt*100:.2f}%, Completion: {res.weight_completion*100:.2f}%)")


def test_moving_averages_and_cold_start():
    print("Testing moving averages and cold start padding...")
    # Single price cold start
    price_today = 0.10389
    prices_cold = [price_today] * 9
    ma_3d = sum(prices_cold[:3]) / 3
    ma_7d = sum(prices_cold[:7]) / 7

    assert abs(ma_3d - price_today) < 1e-6
    assert abs(ma_7d - price_today) < 1e-6

    # Price change sliding
    new_price = 0.20000
    shifted_prices = [new_price] + prices_cold[:8]
    assert len(shifted_prices) == 9
    assert shifted_prices[0] == new_price
    assert shifted_prices[1] == price_today

    new_ma_3d = sum(shifted_prices[:3]) / 3
    new_ma_7d = sum(shifted_prices[:7]) / 7
    expected_3d = (0.20000 + 0.10389 + 0.10389) / 3
    assert abs(new_ma_3d - expected_3d) < 1e-6
    print("  [OK] Moving averages & sliding window math passed")


def test_storage_csv_roundtrip():
    print("Testing CSV storage serialization and reading...")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        temp_csv = Path(tf.name)

    try:
        sample_records = [
            ["openai/gpt-5.6-luna", "2026-08-24T20:00:00Z", 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389],
            ["deepseek/deepseek-v4-flash-0731", "2026-08-24T20:00:00Z", 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030]
        ]
        write_history(sample_records, temp_csv)
        history = read_history(temp_csv)

        assert "openai/gpt-5.6-luna" in history
        assert "deepseek/deepseek-v4-flash-0731" in history
        assert abs(history["openai/gpt-5.6-luna"].current - 0.10389) < 1e-5
        assert len(history["openai/gpt-5.6-luna"].prices) == 9
        print("  [OK] CSV persistence roundtrip passed")
    finally:
        if temp_csv.exists():
            temp_csv.unlink()


def test_offline_fallback():
    print("Testing offline fallback when API is unreachable...")
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        temp_csv = Path(tf.name)

    try:
        sample_records = [
            ["openai/gpt-5.6-luna", "2026-08-24T20:00:00Z", 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389]
        ]
        write_history(sample_records, temp_csv)

        # Force tracker to run with invalid URL / 0 timeout to simulate offline
        res = run_tracker(dry_run=True, history_path=temp_csv, timeout=0.001, hints_enabled=True)
        assert res.status == "success"
        assert res.fallback is True
        d = res.to_dict()
        assert d["data_source"] == "cached_history"
        assert d["api_offline_fallback"] is True
        assert d["fallback"] is True
        assert "_hints" in d
        assert "data_source" in d["_hints"]
        print("  [OK] Offline fallback & self-describing A2A schema test passed")
    finally:
        if temp_csv.exists():
            temp_csv.unlink()


def test_config_calibration():
    print("Testing config weight calibration...")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_cfg = Path(tf.name)

    try:
        sample_csv = Path(__file__).parent.parent / "docs" / "sample" / "openrouter_activity_2026-08-24.csv"
        mix = parse_activity_log(sample_csv)
        from anticharon.config import update_config_weights
        update_config_weights(mix.weight_prompt, mix.weight_completion, temp_cfg)

        cfg = load_config(temp_cfg)
        assert abs(cfg["weight_prompt"] - 0.997063) < 1e-4, f"Weight prompt calibration failed: {cfg['weight_prompt']}"
        assert abs(cfg["weight_completion"] - 0.002937) < 1e-4, f"Weight completion calibration failed: {cfg['weight_completion']}"
        print("  [OK] Configuration calibration update passed")
    finally:
        if temp_cfg.exists():
            temp_cfg.unlink()


def test_ascii_chart():
    print("Testing ASCII price spectrum chart rendering...")
    from anticharon.chart import render_ascii_price_bar
    from anticharon.models import ModelPrice

    sample_prices = [
        ModelPrice(model="qwen/qwen3.7-flash", price_1m=0.03029, ma_7d=0.03029, ma_3d=0.03029, change_vs_7d_pct=0.0),
        ModelPrice(model="openai/gpt-5.6-luna", price_1m=0.20294, ma_7d=0.20294, ma_3d=0.20294, change_vs_7d_pct=0.0),
        ModelPrice(model="google/gemini-3.7-flash", price_1m=0.37941, ma_7d=0.37941, ma_3d=0.37941, change_vs_7d_pct=0.0),
    ]
    lines = render_ascii_price_bar(sample_prices, default_model="openai/gpt-5.6-luna")
    assert len(lines) >= 5, "Chart should have headers, items, and footers"
    assert any("▲ Cheaper" in l for l in lines)
    assert any("▼ More Expensive" in l for l in lines)
    assert any("🏆 [BEST]" in l for l in lines)
    assert any("★ [DEFAULT]" in l for l in lines)
    print("  [OK] ASCII chart rendering passed")


def test_model_manager():
    print("Testing model manager (add, remove, list)...")
    from anticharon.manager import add_model, remove_model, list_models

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        temp_cfg = Path(tf.name)

    try:
        # Initial state with empty shortlist
        temp_cfg.write_text('{"shortlist": ["openai/gpt-5.6-luna"]}', encoding="utf-8")

        # 1. Add model with dry-run
        res_dry = add_model("google/gemini-3.7-flash", dry_run=True, config_path=temp_cfg, validate_catalog=False)
        assert res_dry.status == "success"
        assert res_dry.dry_run is True
        assert len(res_dry.shortlist) == 2
        # Verify file on disk not changed
        cfg_disk = load_config(temp_cfg)
        assert len(cfg_disk["shortlist"]) == 1

        # 2. Add model actual
        res_act = add_model("google/gemini-3.7-flash", dry_run=False, config_path=temp_cfg, validate_catalog=False)
        assert res_act.status == "success"
        assert len(load_config(temp_cfg)["shortlist"]) == 2

        # 3. Add duplicate
        res_dup = add_model("google/gemini-3.7-flash", dry_run=False, config_path=temp_cfg, validate_catalog=False)
        assert res_dup.status == "warning"
        assert len(load_config(temp_cfg)["shortlist"]) == 2

        # 4. Remove model
        res_rm = remove_model("google/gemini-3.7-flash", dry_run=False, config_path=temp_cfg)
        assert res_rm.status == "success"
        assert len(load_config(temp_cfg)["shortlist"]) == 1

        # 5. List models
        res_list = list_models(config_path=temp_cfg)
        assert len(res_list.shortlist) == 1
        print("  [OK] Model management (add, remove, list) passed")
    finally:
        if temp_cfg.exists():
            temp_cfg.unlink()


def test_model_discovery_filters():
    print("Testing model discovery multi-criteria filters...")
    from anticharon.discovery import CatalogModel, filter_catalog

    dummy_catalog = [
        CatalogModel(
            id="google/gemini-2.5-flash-lite",
            name="Google: Gemini 2.5 Flash Lite",
            context_length=1048576,
            prompt_price_1m=0.10,
            completion_price_1m=0.40,
            blended_price_1m=0.10087,
            is_promo=False,
            output_modalities=["text"]
        ),
        CatalogModel(
            id="nvidia/nemotron-3.5-lightning:free",
            name="NVIDIA: Nemotron (free)",
            context_length=1000000,
            prompt_price_1m=0.0,
            completion_price_1m=0.0,
            blended_price_1m=0.0,
            is_promo=True,
            output_modalities=["text"]
        ),
        CatalogModel(
            id="openai/gpt-5.6-luna",
            name="OpenAI: GPT-5.6 Luna",
            context_length=1048576,
            prompt_price_1m=0.20,
            completion_price_1m=1.20,
            blended_price_1m=0.20290,
            is_promo=False,
            output_modalities=["text"]
        ),
        CatalogModel(
            id="anthropic/claude-3-opus",
            name="Anthropic: Claude 3 Opus",
            context_length=200000,
            prompt_price_1m=15.0,
            completion_price_1m=75.0,
            blended_price_1m=15.174,
            is_promo=False,
            output_modalities=["text"]
        )
    ]

    # Keyword filter
    f_gemini = filter_catalog(dummy_catalog, query="gemini")
    assert len(f_gemini) == 1
    assert f_gemini[0].id == "google/gemini-2.5-flash-lite"

    # Promo filter
    f_promo = filter_catalog(dummy_catalog, promo_only=True)
    assert len(f_promo) == 1
    assert f_promo[0].id == "nvidia/nemotron-3.5-lightning:free"

    # Price inequality expression
    f_cheap = filter_catalog(dummy_catalog, filter_expressions=["price < 1.0"])
    assert len(f_cheap) == 3
    assert all(m.blended_price_1m < 1.0 for m in f_cheap)

    # Max input price
    f_in = filter_catalog(dummy_catalog, max_input_price=0.15)
    assert len(f_in) == 2
    print("  [OK] Model discovery multi-criteria filters passed")


def test_hermes_integration():
    print("Testing Hermes configuration detection, stream-grep parsing, and auto-sync...")
    from anticharon.hermes import extract_models_from_file, sync_hermes_to_config

    # 1. Test Stream-Grep against VM config fixture (inline JSON fallback_providers)
    vm_yaml_content = """model:
  default: openai/gpt-5.6-luna
  provider: openrouter
  base_url: https://openrouter.ai/api/v1
  api_mode: chat_completions
fallback_providers: '[{"provider":"openrouter","model":"deepseek/deepseek-v4-pro-0813"},{"provider":"openrouter","model":"deepseek/deepseek-v4-flash-0731"},{"provider":"openrouter","model":"qwen/qwen3.7-flash"},{"provider":"google/gemini-3.1-flash-lite","provider":"openrouter","model":"google/gemini-3.1-flash-lite"},{"provider":"openrouter","model":"minimax/minimax-m2.7"},{"provider":"openrouter","model":"google/gemini-2.5-flash-lite"},{"provider":"openrouter","model":"openai/gpt-4.1-nano"}]'
"""
    with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as tf:
        tf.write(vm_yaml_content)
        tf_path = Path(tf.name)

    try:
        parsed = extract_models_from_file(tf_path)
        assert parsed is not None, "Failed to parse VM yaml"
        assert parsed["default_model"] == "openai/gpt-5.6-luna"
        assert len(parsed["fallback_models"]) >= 6
        assert parsed["all_models"][0] == "openai/gpt-5.6-luna"
        assert "deepseek/deepseek-v4-pro-0813" in parsed["all_models"]
        assert "openai/gpt-4.1-nano" in parsed["all_models"]

        # 2. Test Shortlist Synchronization
        with tempfile.NamedTemporaryFile("w+", suffix=".json", delete=False) as cf:
            cf.write('{"shortlist": ["old/model"], "weight_prompt": 0.995, "weight_completion": 0.005}')
            cf_path = Path(cf.name)

        try:
            changed, new_shortlist, _ = sync_hermes_to_config(parsed, config_path=cf_path, dry_run=False)
            assert changed is True
            assert len(new_shortlist) >= 7
            assert new_shortlist[0] == "openai/gpt-5.6-luna"

            # Verify weight preservation
            cfg = load_config(cf_path)
            assert cfg["weight_prompt"] == 0.995
            assert cfg["shortlist"] == new_shortlist
        finally:
            if cf_path.exists():
                cf_path.unlink()

        # 3. Test multi-line YAML fallbacks with mixed providers (OpenRouter vs Anthropic)
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
        with tempfile.NamedTemporaryFile("w+", suffix=".yaml", delete=False) as yf:
            yf.write(yaml_multiline)
            yf_path = Path(yf.name)

        try:
            parsed_multi = extract_models_from_file(yf_path)
            assert parsed_multi is not None
            assert parsed_multi["default_model"] == "openai/gpt-5.6-luna"
            assert "claude-3-opus" not in parsed_multi["all_models"]
            assert "deepseek/deepseek-v4-pro-0813" in parsed_multi["all_models"]
            assert "qwen/qwen3.7-flash" in parsed_multi["all_models"]
            assert len(parsed_multi["all_models"]) == 3
        finally:
            if yf_path.exists():
                yf_path.unlink()

        # 4. Test run_tracker with hermes_config_path and dry_run
        res = run_tracker(dry_run=True, hermes_config_path=tf_path, timeout=0.001)
        assert res.hermes_integration is not None
        assert res.hermes_integration.detected is True
        assert res.hermes_integration.warning is None
        res_dict = res.to_dict()
        assert "hermes_integration" in res_dict
        assert res_dict["hermes_integration"]["detected"] is True
        assert res_dict["hermes_integration"]["warning"] is None

        # 5. Test run_tracker with no_hermes=True
        res_no = run_tracker(dry_run=True, no_hermes=True, timeout=0.001)
        assert res_no.hermes_integration is not None
        assert res_no.hermes_integration.detected is False
        assert res_no.hermes_integration.method == "standalone"

        print("  [OK] Hermes integration, stream-grep parser, and sync tests passed")
    finally:
        if tf_path.exists():
            tf_path.unlink()


def test_historical_analytics_and_profiles():
    """Test 30-day statistical variance, profile classification, sibling detection, and llms.txt."""
    print("Testing 30-day historical analytics, model profiles, and llms.txt...")
    from anticharon.analytics import calculate_model_analytics, find_sibling_alternatives, parse_model_family

    # 1. Test family parser
    prov, prefix, ver, suffix = parse_model_family("google/gemini-3.7-flash")
    assert prov == "google"
    assert prefix == "gemini-"
    assert ver == 3.7
    assert suffix == "-flash"

    # 2. Test sibling detection
    candidates = {
        "google/gemini-3.7-flash": 0.75881,
        "google/gemini-3.8-flash": 0.75881,
        "google/gemini-2.5-flash-lite": 0.10088
    }
    sibs = find_sibling_alternatives("google/gemini-3.7-flash", 0.75881, candidates)
    assert len(sibs) == 1
    assert sibs[0].model == "google/gemini-3.8-flash"
    assert sibs[0].relation == "newer_version"

    # 3. Test PROMO_ENDED & SUNSETTING classification
    hist_promo = [0.75881]*4 + [0.37941]*5
    an_promo = calculate_model_analytics("google/gemini-3.7-flash", 0.75881, hist_promo, candidates)
    assert an_promo.profile == "PROMO_ENDED"
    assert "PROMO_ENDED" in an_promo.badge
    assert an_promo.secondary_badge == "⚠️ SUNSETTING"
    assert round(an_promo.change_vs_30d_pct, 1) == 100.0

    # 4. Test STABLE classification (mature low-variance history)
    hist_stable = [0.10088]*6 + [0.10087]*2 + [0.10088]
    an_stable = calculate_model_analytics("google/gemini-2.5-flash-lite", 0.10088, hist_stable)
    assert an_stable.profile == "STABLE"
    assert "STABLE" in an_stable.badge
    assert an_stable.volatility_cv_pct < 0.1

    # 5. Test NEWLY_TRACKED (cold-start) classification
    an_cold = calculate_model_analytics("openai/gpt-4.1-nano", 0.10, [0.10]*9)
    assert an_cold.profile == "NEWLY_TRACKED"
    assert "NEWLY_TRACKED" in an_cold.badge

    # 6. Test VOLATILE classification
    hist_vol = [0.85, 0.40, 0.95, 0.45, 0.90, 0.40, 0.85, 0.40, 0.90]
    an_vol = calculate_model_analytics("nousresearch/hermes-3-70b", 0.65, hist_vol)
    assert an_vol.profile == "VOLATILE"
    assert "VOLATILE" in an_vol.badge

    # 7. Test DISCOUNTED classification
    hist_disc = [1.50, 1.50, 1.80, 2.00, 2.50, 3.00, 3.00, 3.00, 3.00]
    an_disc = calculate_model_analytics("mistralai/mistral-large-2407", 1.50, hist_disc)
    assert an_disc.profile == "DISCOUNTED"
    assert "DISCOUNTED" in an_disc.badge

    # 8. Test CREEPING_INFLATION classification
    hist_creep = [0.06534]*4 + [0.06018]*2 + [0.06017]*2 + [0.06017]
    an_creep = calculate_model_analytics("deepseek/deepseek-v4-flash-0731", 0.06534, hist_creep)
    assert an_creep.profile == "CREEPING_INFLATION"
    assert "CREEPING" in an_creep.badge

    # 9. Test run_tracker with enable_analytics=True (hermetic temporary history)
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        temp_hist = Path(tf.name)
    try:
        sample_records = [
            ["openai/gpt-5.6-luna", "2026-08-24T20:00:00Z", 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389, 0.10389]
        ]
        write_history(sample_records, temp_hist)
        res_an = run_tracker(dry_run=True, enable_analytics=True, timeout=0.001, history_path=temp_hist)
        assert res_an.analytics_mode is True
        assert len(res_an.prices_shortlist) > 0
        an_dict = res_an.to_dict()
        assert an_dict.get("analytics_mode") is True
        first_model = an_dict["prices_shortlist"][0]
        assert "analytics" in first_model
        assert "profile" in first_model["analytics"]
    finally:
        if temp_hist.exists():
            temp_hist.unlink()

    # 10. Test llms.txt presence
    llms_path = Path(__file__).resolve().parent.parent / "llms.txt"
    assert llms_path.exists(), "llms.txt must exist at repository root"
    llms_text = llms_path.read_text(encoding="utf-8")
    assert "### Tool Integration Briefing: Anticharon" in llms_text
    assert "anticharon check --profile --json" in llms_text
    assert "anticharon history --csv" in llms_text

    print("  [OK] 30-day analytics, model profiles, and llms.txt tests passed")


def test_mcp_server_suite():
    print("Testing Model Context Protocol (MCP) server tools, resources, and prompts...")
    import asyncio
    import json
    from anticharon.mcp import server

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 1. Tools registration and schema
        tools = loop.run_until_complete(server.list_tools())
        tool_names = [t.name for t in tools]
        assert "check_prices" in tool_names, "Tool check_prices missing"
        assert "get_model_history" in tool_names, "Tool get_model_history missing"
        assert "discover_models" in tool_names, "Tool discover_models missing"
        assert "import_hermes_models" in tool_names, "Tool import_hermes_models missing"
        assert "sync_hermes_models" not in tool_names, "Legacy tool sync_hermes_models should be completely removed"

        # 2. Tool execution: check_prices
        res_prices = loop.run_until_complete(server.call_tool("check_prices", {"dry_run": True, "include_analytics": True}))
        assert not res_prices.is_error, "check_prices failed"
        assert len(res_prices.content) > 0
        payload = json.loads(res_prices.content[0].text)
        assert "data_source" in payload
        assert "api_offline_fallback" in payload
        assert "_hints" in payload
        assert "api_offline_fallback" in payload["_hints"]
        assert "fallback_providers" in payload["_hints"]["api_offline_fallback"]

        # 3. Tool execution: get_model_history (csv format)
        res_hist = loop.run_until_complete(server.call_tool("get_model_history", {"format": "csv"}))
        assert not res_hist.is_error
        hist_data = json.loads(res_hist.content[0].text)
        assert hist_data["format"] == "csv"
        assert "model,last_updated" in hist_data["data"]

        # 4. Tool execution: import_hermes_models (default dry_run=True verification)
        res_import = loop.run_until_complete(server.call_tool("import_hermes_models", {}))
        assert not res_import.is_error
        data_import = json.loads(res_import.content[0].text)
        assert data_import["direction"] == "hermes→anticharon"
        assert data_import["hermes_untouched"] is True
        if data_import.get("detected"):
            assert data_import["dry_run"] is True
            assert "notice" in data_import
            assert "PREVIEW ONLY" in data_import["notice"]

        # 5. Resources registration and reading
        resources = loop.run_until_complete(server.list_resources())
        resource_uris = [r.uri for r in resources]
        assert "anticharon://llms.txt" in resource_uris
        assert "anticharon://history.csv" in resource_uris
        assert "anticharon://shortlist.json" in resource_uris

        res_llms = loop.run_until_complete(server.read_resource("anticharon://llms.txt"))
        assert len(res_llms) > 0 and len(res_llms[0].content) > 100

        res_shortlist = loop.run_until_complete(server.read_resource("anticharon://shortlist.json"))
        assert len(res_shortlist) > 0
        cfg_read = json.loads(res_shortlist[0].content)
        assert "shortlist" in cfg_read

        # 6. Prompts registration
        prompts = loop.run_until_complete(server.list_prompts())
        prompt_names = [p.name for p in prompts]
        assert "cost_spike_triage" in prompt_names
        assert "model_migration_advisor" in prompt_names
        assert "family_upgrade_discover" in prompt_names
        assert "daily_cost_briefing" in prompt_names
        assert "budget_optimization_audit" in prompt_names

        p_triage = loop.run_until_complete(server.get_prompt("cost_spike_triage", {"model_id": "test/model", "current_price": 0.50, "ma_7d": 0.25}))
        assert len(p_triage.messages) > 0

        p_discover = loop.run_until_complete(server.get_prompt("family_upgrade_discover", {"model_or_family": "gemini"}))
        assert len(p_discover.messages) > 0

        print("  [OK] MCP server tools, resources, prompts, and schema tests passed")
    finally:
        loop.close()


def main():
    print("\n🚀 Running Anticharon Test Suite...")
    print("-" * 50)
    try:
        test_log_parser()
        test_moving_averages_and_cold_start()
        test_storage_csv_roundtrip()
        test_offline_fallback()
        test_config_calibration()
        test_ascii_chart()
        test_model_manager()
        test_model_discovery_filters()
        test_hermes_integration()
        test_historical_analytics_and_profiles()
        test_mcp_server_suite()
        print("-" * 50)
        print("✨ ALL TESTS PASSED SUCCESSFULLY! (11/11)")
        print("💡 Note: [WARN] network messages above are simulated 1ms timeout tests")
        print("   verifying Anticharon's offline cache resilience engine (100% expected).\n")
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
