"""Tests for anticharon.mcp: FastMCP server tools/resources/prompts.

Marked @pytest.mark.live: check_prices (and get_model_history) call run_tracker
without mocking the network, so this exercises the real OpenRouter API contract.
Excluded from the default `uv run pytest` gate per EXECUTION_CONTRACT.md.

The deterministic (mocked, no network) tests below cover PE2-006's "MCP suite
is live-only and does not deterministically assert the complete three-price
payload" gap -- see docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-006.
"""

import asyncio
import json

import pytest

from anticharon.mcp import server


@pytest.mark.live
def test_mcp_server_suite():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        # 1. Tools registration and schema
        tools = loop.run_until_complete(server.list_tools())
        tool_names = [t.name for t in tools]
        assert "check_prices" in tool_names
        assert "get_model_history" in tool_names
        assert "discover_models" in tool_names
        assert "import_hermes_models" in tool_names
        assert "sync_hermes_models" not in tool_names

        # 2. Tool execution: check_prices
        res_prices = loop.run_until_complete(server.call_tool("check_prices", {"dry_run": True, "include_analytics": True}))
        assert not res_prices.is_error
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
            assert "notice" not in data_import
            assert "PREVIEW_ONLY" in [m["code"] for m in data_import["messages"]]

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
    finally:
        loop.close()


def _run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# --- GH-4: import_hermes_models MCP tool payload must warn and preserve the
# shortlist on an equal-length-different incomplete detection (deterministic,
# calls the plain function directly -- no live network, no event loop needed
# since it isn't async). ---


def test_import_hermes_models_warns_and_preserves_shortlist_on_equal_length_incomplete(monkeypatch, tmp_path):
    from anticharon.mcp import import_hermes_models

    existing = ["openai/gpt-5.6-luna", "qwen/qwen3.7-flash", "openai/gpt-4.1-nano"]
    partial = ["openai/gpt-5.6-luna", "deepseek/deepseek-v4-flash-0731", "mistralai/mistral-small-3.2"]
    assert len(partial) == len(existing) and partial != existing

    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({"shortlist": list(existing)}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg_path))

    monkeypatch.setattr(
        "anticharon.mcp.get_hermes_models",
        lambda custom_path=None, prompt_if_missing=False: {
            "source": "cli:hermes",
            "method": "cli",
            "detection": "incomplete",
            "default_model": partial[0],
            "fallback_models": partial[1:],
            "all_models": list(partial),
        },
    )

    result = import_hermes_models(dry_run=False)

    assert result["status"] == "warning"
    assert result["detection"] == "incomplete"
    assert "warning" not in result
    assert "HERMES_INCOMPLETE" in [m["code"] for m in result["messages"]]
    assert result["changed"] is False
    assert result["shortlist"] == existing
    assert "deepseek/deepseek-v4-flash-0731" not in result["shortlist"]
    from anticharon.config import load_config
    assert load_config(cfg_path)["shortlist"] == existing


def test_check_prices_zdr_preserves_three_price_distinction_deterministic(monkeypatch, tmp_path):
    """Deterministic (mocked, no network) coverage of PE2-001/PE2-003's fix
    surviving through the actual MCP tool boundary, not just run_tracker
    directly -- check_prices(zdr_only=True) must return effective_price_1m
    and policy_price_1m as distinct values in its JSON payload."""
    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({
        "shortlist": ["openai/gpt-5.6-sol"],
        "weight_uncached_prompt": 0.232622,
        "weight_cached_prompt": 0.764478,
        "weight_completion": 0.0029,
    }), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg_path))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "openai/gpt-5.6-sol": {
            "id": "openai/gpt-5.6-sol",
            "canonical_slug": "openai/gpt-5.6-sol-20260709",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [
        {"provider_name": "OpenAI", "pricing": {"prompt": "0.000001", "completion": "0.000005"},
         "provider_info": {"dataPolicy": {"retainsPrompts": True}}},
        {"provider_name": "Azure", "pricing": {"prompt": "0.000005", "completion": "0.00003"},
         "provider_info": {"dataPolicy": {"retainsPrompts": False}}},
    ])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})

    res = _run_async(server.call_tool("check_prices", {"dry_run": True, "zdr_only": True, "force_refresh": True}))
    assert not res.is_error
    payload = json.loads(res.content[0].text)

    model = payload["prices_shortlist"][0]
    assert model["effective_price_1m"] != model["policy_price_1m"]
    assert model["policy_price_1m"] > model["effective_price_1m"]
    assert model["is_policy_routable"] is True


def test_check_prices_zdr_unroutable_never_recommended_deterministic(monkeypatch, tmp_path):
    """Deterministic MCP-boundary coverage of PE2-001's BEST_OPTION_CHANGED fix."""
    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({
        "shortlist": ["provider/expensive-default", "provider/cheap-unroutable"],
        "weight_uncached_prompt": 0.232622,
        "weight_cached_prompt": 0.764478,
        "weight_completion": 0.0029,
    }), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg_path))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "provider/expensive-default": {
            "id": "provider/expensive-default", "canonical_slug": "provider/expensive-default",
            "pricing": {"prompt": "0.000002", "completion": "0.00001"},
        },
        "provider/cheap-unroutable": {
            "id": "provider/cheap-unroutable", "canonical_slug": "provider/cheap-unroutable",
            "pricing": {"prompt": "0.0000001", "completion": "0.0000005"},
        },
    })

    def fake_endpoints(canonical_slug, timeout=10.0):
        if canonical_slug == "provider/expensive-default":
            return [{"provider_name": "Azure", "pricing": {"prompt": "0.000005", "completion": "0.00003"},
                     "provider_info": {"dataPolicy": {"retainsPrompts": False}}}]
        return [{"provider_name": "OpenAI", "pricing": {"prompt": "0.0000001", "completion": "0.0000005"},
                 "provider_info": {"dataPolicy": {"retainsPrompts": True}}}]

    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", fake_endpoints)
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})

    res = _run_async(server.call_tool("check_prices", {"dry_run": True, "zdr_only": True, "force_refresh": True}))
    assert not res.is_error
    payload = json.loads(res.content[0].text)

    model_ids_in_order = [m["model"] for m in payload["prices_shortlist"]]
    assert model_ids_in_order[0] == "provider/expensive-default"  # the only confirmed-routable model

    warning_types_by_model = {
        w["model"]: w["type"] for w in payload["price_warnings"] if w.get("model") == "provider/cheap-unroutable"
    }
    assert warning_types_by_model.get("provider/cheap-unroutable") == "POLICY_UNROUTABLE"
    best_option_warnings = [w for w in payload["price_warnings"] if w["type"] == "BEST_OPTION_CHANGED"]
    assert all(w.get("suggested_cheapest") != "provider/cheap-unroutable" for w in best_option_warnings)
