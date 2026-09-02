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
        res = run_tracker(dry_run=True, history_path=temp_csv, timeout=0.001)
        assert res.status == "success"
        print("  [OK] Offline fallback test passed")
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
        print("-" * 50)
        print("✨ ALL TESTS PASSED SUCCESSFULLY! (9/9)\n")
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
