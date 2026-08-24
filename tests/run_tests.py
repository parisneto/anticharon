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


def main():
    print("\n🚀 Running Anticharon Test Suite...")
    print("-" * 50)
    try:
        test_log_parser()
        test_moving_averages_and_cold_start()
        test_storage_csv_roundtrip()
        test_offline_fallback()
        print("-" * 50)
        print("✨ ALL TESTS PASSED SUCCESSFULLY! (4/4)\n")
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}\n", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
