"""AC-3 / E-4: `run`, `history`, CLI, MCP, and agent prompts report the same
analytics for the same stored evidence; local reads source prices from
`effective_prices.json` (history.csv is only a cached-quote fallback)."""

import argparse
import asyncio
import io
import json
from contextlib import redirect_stdout
from datetime import date, datetime, timedelta, timezone

import pytest

from anticharon.cli import cmd_check, cmd_history
from anticharon.mcp import server
from anticharon.prompts import PROMPTS
from anticharon.storage import write_history
from anticharon.tracker import read_check_result, read_history_result, run_tracker

MODEL = "openai/gpt-5.6-sol"
NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


@pytest.fixture
def env(monkeypatch, tmp_path):
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": MODEL, "source": "manual"}]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)

    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("anticharon.tracker.datetime", _Frozen)
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history",
                        lambda *a, **kw: pytest.fail("fresh store must not refetch"))
    return tmp_path, cfg


def seed(tmp_path, days_ago, price=1.0):
    (tmp_path / "effective_prices.json").write_text(json.dumps({MODEL: {
        "canonical_slug": f"{MODEL}-20260709", "first_seen": TODAY.isoformat(),
        "last_synced": NOW.isoformat(),
        "observations": [{"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": price}
                         for n in days_ago],
    }}), encoding="utf-8")


def export_quote(tmp_path, quote):
    write_history([[MODEL, NOW.isoformat(), quote, quote, quote, quote, quote] + [None] * 9],
                  tmp_path / "history.csv")


def _json_analytics(payload):
    return payload["prices_shortlist"][0]["analytics"]


def _cli_json(fn, **kw):
    buf = io.StringIO()
    args = argparse.Namespace(json=True, no_hermes=True, config=None, data_dir=None, hermes_config=None,
                              hints=False, model_id=None, csv=False, history_csv=False, **kw)
    with redirect_stdout(buf):
        assert fn(args) == 0
    return json.loads(buf.getvalue())


def test_cli_mcp_and_library_report_identical_analytics(env):
    tmp_path, _ = env
    seed(tmp_path, range(1, 30))
    export_quote(tmp_path, 2.0)

    library = read_history_result(no_hermes=True).prices_shortlist[0].analytics.to_dict()
    cli = _json_analytics(_cli_json(cmd_history))
    mcp = _json_analytics(json.loads(asyncio.run(server.call_tool("get_model_history", {})).content[0].text))

    assert cli == mcp == library
    assert library["observation_count"] == 29
    assert library["profile"] != "NEWLY_TRACKED"
    assert library["classification_reason"].startswith("29 distinct observed days ≥ 14")


def test_run_and_history_classify_identical_stored_evidence_identically(env, monkeypatch):
    tmp_path, cfg = env
    seed(tmp_path, range(1, 30))
    export_quote(tmp_path, 2.0)
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        MODEL: {"id": MODEL, "canonical_slug": f"{MODEL}-20260709",
                "pricing": {"prompt": "0.000002", "completion": "0.00001"}},
    })
    live = run_tracker(dry_run=True, config_path=cfg, history_path=tmp_path / "history.csv",
                       no_hermes=True, enable_analytics=True).prices_shortlist[0]
    local = read_history_result(no_hermes=True).prices_shortlist[0]
    assert live.analytics.to_dict() == local.analytics.to_dict()


def test_local_reads_work_from_the_store_without_history_csv(env):
    tmp_path, _ = env
    seed(tmp_path, range(30), price=0.5)  # includes today
    assert not (tmp_path / "history.csv").exists()

    check = read_check_result(no_hermes=True)
    history = read_history_result(no_hermes=True)

    for result in (check, history):
        row = result.prices_shortlist[0]
        assert (row.price_1m, row.ma_7d, row.price_source, row.price_date) == (
            0.5, 0.5, "observation", TODAY.isoformat())
        assert "DATA_STALE" not in [m.code for m in result.messages]
    assert history.prices_shortlist[0].analytics.current_price_source == "observation"


def test_stale_store_reports_data_stale_and_cached_quote_covers_unobserved_models(env):
    tmp_path, _ = env
    seed(tmp_path, range(3, 10))  # latest observation is three days old
    assert "DATA_STALE" in [m.code for m in read_check_result(no_hermes=True).messages]

    seed(tmp_path, [])  # model with no observations falls back to the exported quote
    export_quote(tmp_path, 2.0)
    row = read_history_result(no_hermes=True).prices_shortlist[0]
    assert (row.price_1m, row.price_source) == (2.0, "cached_quote")
    assert row.analytics.profile == "NEWLY_TRACKED"
    assert row.analytics.observation_count == 0


def test_human_output_shows_evidence_and_price_provenance(env):
    tmp_path, _ = env
    seed(tmp_path, range(1, 30))
    buf = io.StringIO()
    args = argparse.Namespace(json=False, no_hermes=True, config=None, data_dir=None, hermes_config=None,
                              hints=False, model_id=None, csv=False, history_csv=False)
    with redirect_stdout(buf):
        cmd_history(args)
    out = buf.getvalue()
    assert "29 observed days" in out
    assert "price: observation" in out


def test_agent_prompt_distinguishes_backfill_from_insufficient_history():
    text = PROMPTS["budget_optimization_audit"].render()
    assert "classification_reason" in text and "observation_count" in text
    assert "insufficient history" in text and "backfilled" in text
    assert "change_vs_30d_pct: null" in text


def test_price_provenance_and_evidence_fields_are_in_check_json(env):
    tmp_path, _ = env
    seed(tmp_path, range(1, 15))
    payload = _cli_json(cmd_check)
    row = payload["prices_shortlist"][0]
    assert row["price_source"] == "observation"
    assert date.fromisoformat(row["price_date"]) == TODAY - timedelta(days=1)
