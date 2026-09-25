"""Self-test and runtime environment validation for Anticharon."""

import sys
import time
from pathlib import Path

import requests

from anticharon.config import get_config_path, get_data_dir, load_config
from anticharon.hermes import get_hermes_models, hermes_detection_messages, hermes_shortlist_divergent
from anticharon.models import AgentMessage, build_envelope, render_messages
from anticharon.pricing import calculate_effective_cost, price_per_1m
from anticharon.tracker import OPENROUTER_MODELS_URL


def run_self_test(
    hermes_config_path: str | Path | None = None,
    no_hermes: bool = False,
    json_mode: bool = False
) -> bool:
    """Run comprehensive self-checks on runtime, config, formulas, permissions, network, and Hermes."""
    import json
    import platform
    started = time.perf_counter()
    all_passed = True
    diag: dict = {}
    messages: list[AgentMessage] = []

    # Environment & Host Resolution
    os_name = platform.system()
    os_release = platform.release()
    os_arch = platform.machine()
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 10)
    py_bin = sys.executable
    try:
        resolved_data_dir = str(get_data_dir())
    except Exception:
        resolved_data_dir = "unresolved"
    try:
        resolved_cfg_path = str(get_config_path())
    except Exception:
        resolved_cfg_path = "unresolved"

    diag["environment"] = {
        "os": os_name,
        "release": os_release,
        "architecture": os_arch,
        "python_version": py_ver,
        "python_executable": py_bin,
        "data_dir": resolved_data_dir,
        "config_path": resolved_cfg_path
    }

    if not json_mode:
        print("\n🪙  Anticharon Self-Test & Diagnostic Suite\n" + "=" * 60)
        print(f" 🖥️  Host System:  {os_name} {os_release} ({os_arch})")
        print(f" 🐍 Python Env:   v{py_ver} ({py_bin})")
        print(f" 📁 Data Storage: {resolved_data_dir}")
        print(f" ⚙️  Config Path:  {resolved_cfg_path}")
        print("-" * 60)

    # 1. Python Environment Check
    diag["python"] = {"version": py_ver, "supported": py_ok}
    if py_ok:
        if not json_mode:
            print(f" [PASS] Python Version: v{py_ver} (Supported)")
    else:
        if not json_mode:
            print(f" [FAIL] Python Version: v{py_ver} (Requires >= 3.10)")
        all_passed = False

    # 2. Config Resolution & Parsing
    shortlist: list = []
    try:
        cfg_path = get_config_path()
        cfg = load_config(cfg_path)
        shortlist = cfg.get("shortlist", [])
        w_uncached = cfg.get("weight_uncached_prompt", 0.232622)
        w_cached = cfg.get("weight_cached_prompt", 0.764478)
        w_out = cfg.get("weight_completion", 0.0029)
        diag["configuration"] = {
            "path": str(cfg_path),
            "models_count": len(shortlist),
            "weight_uncached_prompt": w_uncached,
            "weight_cached_prompt": w_cached,
            "weight_completion": w_out
        }
        if not json_mode:
            print(
                f" [PASS] Configuration: {len(shortlist)} models shortlisted "
                f"(Uncached: {w_uncached*100:.2f}%, Cached: {w_cached*100:.2f}%, Out: {w_out*100:.2f}%)"
            )
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
                # Issue #4: a detected-but-divergent (or incomplete) Hermes state
                # must be flagged, never reported as an unqualified pass. Same
                # check and messages as run/check (A2A-6).
                h_models = h_info.get("all_models", [])
                h_messages = hermes_detection_messages(h_info, shortlist)
                messages.extend(h_messages)

                diag["hermes_integration"] = {
                    "detected": True,
                    "method": h_info.get("method"),
                    "source": h_info.get("source"),
                    "models_count": len(h_models),
                    "detection": h_info.get("detection", "complete"),
                    "shortlist_divergence": hermes_shortlist_divergent(h_models, shortlist),
                }
                if not json_mode:
                    label = "WARN" if h_messages else "PASS"
                    print(f" [{label}] Hermes Integration: Detected ({len(h_models)} models via {h_info.get('method')} from {h_info.get('source')})")
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
    # PE2-007 (corrected 2026-09-17): this previously evaluated an arbitrary
    # `(1.0 * 0.99) + (2.0 * 0.01)` two-component calculation that had no
    # connection to the production pricing function at all -- it would still
    # report "Verified" even if the real cache-aware three-component formula
    # (ADR-2026-0002-TOKENS-CACHED) regressed or were removed entirely. Now
    # calls the actual production function, `calculate_effective_cost`, with
    # two of the ADR's independently-derived golden cases (also used verbatim,
    # unrounded, in tests/test_golden_pricing.py) as reference values:
    #   - Golden Case #1 (cache-heavy, 85% cached): fails if cached-token
    #     pricing is ignored/omitted -- a 2-component blend would compute
    #     roughly $2.04/1M here, not the correct $0.5174/1M.
    #   - Golden Case #4 (zero-cache): the cache-aware and legacy formulas
    #     agree exactly here, confirming the new formula didn't break the
    #     uncached/zero-cache path while fixing the cached one.
    try:
        cache_heavy_cost = calculate_effective_cost(
            uncached_prompt_price_1m=2.00, cache_read_price_1m=0.20, completion_price_1m=10.00,
            uncached_tokens=30_000, cached_tokens=170_000, completion_tokens=1_000,
        )
        cache_heavy_per_1m = price_per_1m(cache_heavy_cost, 30_000 + 170_000 + 1_000)
        assert abs(cache_heavy_per_1m - 0.5174) < 1e-3, "Cache-aware pricing formula mismatch (cache-heavy case)"

        zero_cache_cost = calculate_effective_cost(
            uncached_prompt_price_1m=2.00, cache_read_price_1m=0.20, completion_price_1m=10.00,
            uncached_tokens=50_000, cached_tokens=0, completion_tokens=2_000,
        )
        zero_cache_per_1m = price_per_1m(zero_cache_cost, 50_000 + 2_000)
        assert abs(zero_cache_per_1m - 2.3077) < 1e-3, "Cache-aware pricing formula mismatch (zero-cache case)"

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

    # 7. MCP Server Readiness Check
    try:
        import asyncio

        from anticharon.mcp import server
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            tools = loop.run_until_complete(server.list_tools())
            resources = loop.run_until_complete(server.list_resources())
            tool_names = [t.name for t in tools]
            diag["mcp_server"] = {
                "ready": True,
                "tools_count": len(tools),
                "tools": tool_names,
                "resources_count": len(resources)
            }
            if not json_mode:
                print(f" [PASS] MCP Server: Ready ({len(tools)} tools, {len(resources)} resources loaded)")
        finally:
            loop.close()
    except Exception as e:
        diag["mcp_server"] = {"ready": False, "error": str(e)}
        if not json_mode:
            print(f" [FAIL] MCP Server Error: {e}")
        all_passed = False

    if not all_passed:
        messages.append(AgentMessage(
            "error", "SELF_TEST_FAILED",
            "One or more self-test checks failed; see each check's `error` field for the cause.",
        ))
    diag["all_passed"] = all_passed
    envelope = build_envelope({"status": "success" if all_passed else "error", **diag}, messages, started)

    if json_mode:
        print(json.dumps(envelope, indent=2))
    else:
        print("=" * 60)
        render_messages(envelope["messages"])
        if all_passed:
            print("🎉 All core diagnostics passed successfully!\n")
        else:
            print("⚠️ Some diagnostics failed. Please inspect the errors above.\n")

    return all_passed
