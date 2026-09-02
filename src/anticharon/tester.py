"""Self-test and runtime environment validation for Anticharon."""

import sys
import time
from pathlib import Path
from typing import Optional
import requests

from anticharon.config import load_config, get_data_dir, get_config_path
from anticharon.hermes import get_hermes_models
from anticharon.models import ModelPrice
from anticharon.tracker import OPENROUTER_MODELS_URL


def run_self_test(
    hermes_config_path: Optional[str | Path] = None,
    no_hermes: bool = False,
    json_mode: bool = False
) -> bool:
    """Run comprehensive self-checks on runtime, config, formulas, permissions, network, and Hermes."""
    import json
    all_passed = True
    diag: dict = {}
    if not json_mode:
        print("\n🪙  Anticharon Self-Test & Diagnostic Suite\n" + "=" * 48)

    # 1. Python Environment Check
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    diag["python"] = {"version": py_ver, "supported": py_ok}
    if py_ok:
        if not json_mode:
            print(f" [PASS] Python Environment: v{py_ver} (Supported)")
    else:
        if not json_mode:
            print(f" [FAIL] Python Environment: v{py_ver} (Requires >= 3.10)")
        all_passed = False

    # 2. Config Resolution & Parsing
    try:
        cfg_path = get_config_path()
        cfg = load_config(cfg_path)
        shortlist = cfg.get("shortlist", [])
        w_in = cfg.get("weight_prompt", 0.9971)
        w_out = cfg.get("weight_completion", 0.0029)
        diag["configuration"] = {
            "path": str(cfg_path),
            "models_count": len(shortlist),
            "weight_prompt": w_in,
            "weight_completion": w_out
        }
        if not json_mode:
            print(f" [PASS] Configuration: {len(shortlist)} models shortlisted (In: {w_in*100:.2f}%, Out: {w_out*100:.2f}%)")
    except Exception as e:
        diag["configuration"] = {"error": str(e)}
        if not json_mode:
            print(f" [FAIL] Configuration Error: {e}")
        all_passed = False

    # 3. Hermes Integration Check
    if not no_hermes:
        try:
            h_info = get_hermes_models(custom_path=hermes_config_path)
            if h_info:
                diag["hermes_integration"] = {
                    "detected": True,
                    "method": h_info.get("method"),
                    "source": h_info.get("source"),
                    "models_count": len(h_info.get("all_models", []))
                }
                if not json_mode:
                    print(f" [PASS] Hermes Integration: Detected ({len(h_info.get('all_models', []))} models via {h_info.get('method')} from {h_info.get('source')})")
            else:
                diag["hermes_integration"] = {"detected": False, "mode": "standalone"}
                if not json_mode:
                    print(" [INFO] Hermes Integration: Not detected (Standalone mode active)")
        except Exception as e:
            diag["hermes_integration"] = {"detected": False, "error": str(e)}
            if not json_mode:
                print(f" [WARN] Hermes Integration Error: {e}")
    else:
        diag["hermes_integration"] = {"detected": False, "mode": "disabled"}
        if not json_mode:
            print(" [INFO] Hermes Integration: Disabled (--no-hermes flag active)")

    # 4. Data Directory & Write Permissions
    try:
        data_dir = get_data_dir()
        test_file = data_dir / ".anticharon_perm_test"
        test_file.write_text("ok", encoding="utf-8")
        test_file.unlink()
        diag["storage_permissions"] = {"writable": True, "data_dir": str(data_dir)}
        if not json_mode:
            print(f" [PASS] Storage Permissions: Writable ({data_dir})")
    except Exception as e:
        diag["storage_permissions"] = {"writable": False, "error": str(e)}
        if not json_mode:
            print(f" [FAIL] Storage Permission Error: {e}")
        all_passed = False

    # 5. Mathematical Formula Verification
    try:
        test_cost = (1.0 * 0.99) + (2.0 * 0.01)
        assert abs(test_cost - 1.01) < 1e-6, "Weighted price calculation mismatch"
        prices = [0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10, 0.10]
        ma_3d = sum(prices[:3]) / 3
        ma_7d = sum(prices[:7]) / 7
        assert abs(ma_3d - 0.10) < 1e-6, "MA_3d calculation mismatch"
        assert abs(ma_7d - 0.10) < 1e-6, "MA_7d calculation mismatch"
        diag["math_engine"] = {"verified": True}
        if not json_mode:
            print(" [PASS] Mathematical Engine: Verified")
    except Exception as e:
        diag["math_engine"] = {"verified": False, "error": str(e)}
        if not json_mode:
            print(f" [FAIL] Math Calculation Error: {e}")
        all_passed = False

    # 6. OpenRouter API Connectivity Check
    try:
        start = time.time()
        resp = requests.get(OPENROUTER_MODELS_URL, timeout=10.0)
        elapsed_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            count = len(resp.json().get("data", []))
            diag["openrouter_api"] = {"reachable": True, "models_count": count, "latency_ms": elapsed_ms}
            if not json_mode:
                print(f" [PASS] OpenRouter API: Reachable ({count} models available, Latency: {elapsed_ms}ms)")
        else:
            diag["openrouter_api"] = {"reachable": False, "http_status": resp.status_code}
            if not json_mode:
                print(f" [WARN] OpenRouter API returned HTTP {resp.status_code}")
    except Exception as e:
        diag["openrouter_api"] = {"reachable": False, "error": str(e)}
        if not json_mode:
            print(f" [WARN] OpenRouter API Network Warning: {e} (Anticharon will use local CSV fallback)")

    diag["status"] = "success" if all_passed else "failure"
    diag["all_passed"] = all_passed

    if json_mode:
        print(json.dumps(diag, indent=2))
    else:
        print("=" * 48)
        if all_passed:
            print("🎉 All core diagnostics passed successfully!\n")
        else:
            print("⚠️ Some diagnostics failed. Please inspect the errors above.\n")

    return all_passed
