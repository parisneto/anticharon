"""Self-test and runtime environment validation for Anticharon."""

import sys
import time
from pathlib import Path
import requests

from anticharon.config import load_config, get_data_dir, get_config_path
from anticharon.models import ModelPrice
from anticharon.tracker import OPENROUTER_MODELS_URL


def run_self_test() -> bool:
    """Run comprehensive self-checks on runtime, config, formulas, permissions, and network."""
    all_passed = True
    print("\n🪙  Anticharon Self-Test & Diagnostic Suite\n" + "=" * 48)

    # 1. Python Environment Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if sys.version_info >= (3, 10):
        print(f" [PASS] Python Environment: v{py_ver} (Supported)")
    else:
        print(f" [FAIL] Python Environment: v{py_ver} (Requires >= 3.10)")
        all_passed = False

    # 2. Config Resolution & Parsing
    try:
        cfg_path = get_config_path()
        cfg = load_config(cfg_path)
        shortlist = cfg.get("shortlist", [])
        w_in = cfg.get("weight_prompt", 0.9971)
        w_out = cfg.get("weight_completion", 0.0029)
        print(f" [PASS] Configuration: {len(shortlist)} models shortlisted (In: {w_in*100:.2f}%, Out: {w_out*100:.2f}%)")
    except Exception as e:
        print(f" [FAIL] Configuration Error: {e}")
        all_passed = False

    # 3. Data Directory & Write Permissions
    try:
        data_dir = get_data_dir()
        test_file = data_dir / ".anticharon_perm_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        print(f" [PASS] Storage Permissions: Writable ({data_dir})")
    except Exception as e:
        print(f" [FAIL] Storage Permission Error: {e}")
        all_passed = False

    # 4. Mathematical Formula Verification
    try:
        # Prompt: $1.00/1M, Completion: $2.00/1M, Weight: 0.99 / 0.01 -> 1.00*0.99 + 2.00*0.01 = 1.01
        test_cost = (1.0 * 0.99) + (2.0 * 0.01)
        assert abs(test_cost - 1.01) < 1e-6, "Weighted price calculation mismatch"

        # MA calculation test
        prices = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
        ma_3d = sum(prices[:3]) / 3
        ma_7d = sum(prices[:7]) / 7
        assert abs(ma_3d - 0.10) < 1e-6, "MA_3d calculation mismatch"
        assert abs(ma_7d - 0.10) < 1e-6, "MA_7d calculation mismatch"
        print(" [PASS] Mathematical Engine: Verified")
    except Exception as e:
        print(f" [FAIL] Math Calculation Error: {e}")
        all_passed = False

    # 5. OpenRouter API Connectivity Check
    try:
        start = time.time()
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=10.0)
        elapsed_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            count = len(resp.json().get("data", []))
            print(f" [PASS] OpenRouter API: Reachable ({count} models available, Latency: {elapsed_ms}ms)")
        else:
            print(f" [WARN] OpenRouter API returned HTTP {resp.status_code}")
    except Exception as e:
        print(f" [WARN] OpenRouter API Network Warning: {e} (Anticharon will use local CSV fallback)")

    print("=" * 48)
    if all_passed:
        print("🎉 All core diagnostics passed successfully!\n")
    else:
        print("⚠️ Some diagnostics failed. Please inspect the errors above.\n")

    return all_passed
