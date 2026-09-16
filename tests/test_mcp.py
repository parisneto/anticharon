"""Tests for anticharon.mcp: FastMCP server tools/resources/prompts.

Marked @pytest.mark.live: check_prices (and get_model_history) call run_tracker
without mocking the network, so this exercises the real OpenRouter API contract.
Excluded from the default `uv run pytest` gate per EXECUTION_CONTRACT.md.
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
    finally:
        loop.close()
