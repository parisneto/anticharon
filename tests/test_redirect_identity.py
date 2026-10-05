"""AC-4 / D-4–D-6: redirect and unresolved slug identity.

A slug absent from the catalog but listed as `~<slug>` is a redirect alias: it is
persisted as such, shown as NOT_TRACKED (no price, no history, slug unchanged),
and not re-resolved within 24 hours unless forced.
"""

import argparse
import asyncio
import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import pytest

from anticharon.cli import cmd_check, cmd_history
from anticharon.mcp import server
from anticharon.tracker import read_check_result, read_history_result, run_tracker

OK = "acme/ok"
REDIRECT = "acme/model-latest"
NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)


def _catalog(*ids):
    return {i: {"id": i, "canonical_slug": f"{i}-20260709",
                "pricing": {"prompt": "0.000002", "completion": "0.00001"}} for i in ids}


@pytest.fixture
def env(monkeypatch, tmp_path):
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": OK, "source": "manual"},
                                             {"model": REDIRECT, "source": "hermes", "order": 0}]}),
                   encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    clock = {"now": NOW}
    calls = []

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock["now"]

    monkeypatch.setattr("anticharon.tracker.datetime", _Clock)
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing",
                        lambda slug, *a, **kw: calls.append(("endpoints", slug)) or [])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history",
                        lambda slug, *a, **kw: calls.append(("history", slug)) or {})
    return tmp_path, cfg, clock, calls


def _run(monkeypatch, env, catalog, **kw):
    tmp_path, cfg, _, _ = env
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: catalog)
    return run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True, **kw)


def _store(tmp_path):
    return json.loads((tmp_path / "effective_prices.json").read_text(encoding="utf-8"))


def test_first_detection_persists_redirect_and_reports_not_tracked(monkeypatch, env):
    tmp_path, cfg, _, calls = env
    result = _run(monkeypatch, env, _catalog(OK, f"~{REDIRECT}"))

    [row] = result.not_tracked
    assert (row.model, row.identity, row.resolved_id, row.code) == (
        REDIRECT, "redirect", f"~{REDIRECT}", "REDIRECT_IDENTITY")
    assert row.is_default and row.source == "hermes"
    assert [p.model for p in result.prices_shortlist] == [OK]
    assert "REDIRECT_IDENTITY" in [m.code for m in result.messages]
    # No catalog/history lookups for the redirect identity, and the slug is untouched.
    assert all(slug != REDIRECT and not slug.startswith("~") for _, slug in calls)
    assert [e["model"] for e in json.loads(cfg.read_text(encoding="utf-8"))["shortlist"]] == [OK, REDIRECT]
    stored = _store(tmp_path)[REDIRECT]
    assert (stored["identity"], stored["resolved_id"]) == ("redirect", f"~{REDIRECT}")
    assert "observations" not in stored and "canonical_slug" not in stored
    assert _store(tmp_path)[OK]["identity"] == "exact"


def test_state_is_reused_for_24_hours_then_reresolved_or_forced(monkeypatch, env):
    tmp_path, _, clock, _ = env
    _run(monkeypatch, env, _catalog(OK, f"~{REDIRECT}"))
    first_checked = _store(tmp_path)[REDIRECT]["identity_checked"]

    # Within 24h the alias vanishing is not noticed: the stored state is reused, nothing rewritten.
    clock["now"] = NOW + timedelta(hours=23)
    reused = _run(monkeypatch, env, _catalog(OK))
    assert [(m.identity, m.code) for m in reused.not_tracked] == [("redirect", "REDIRECT_IDENTITY")]
    assert _store(tmp_path)[REDIRECT]["identity_checked"] == first_checked

    # --force re-resolves immediately.
    forced = _run(monkeypatch, env, _catalog(OK), force=True)
    assert [(m.identity, m.code) for m in forced.not_tracked] == [("unresolved", "NO_EXACT_MATCH")]
    assert _store(tmp_path)[REDIRECT]["identity_checked"] != first_checked

    # After 24h an unforced run re-resolves too (the alias is back).
    clock["now"] = NOW + timedelta(hours=49)
    again = _run(monkeypatch, env, _catalog(OK, f"~{REDIRECT}"))
    assert [(m.identity, m.resolved_id) for m in again.not_tracked] == [("redirect", f"~{REDIRECT}")]


def test_unresolved_slug_is_not_tracked_with_no_exact_match(monkeypatch, env):
    result = _run(monkeypatch, env, _catalog(OK))
    [row] = result.not_tracked
    assert (row.identity, row.resolved_id, row.code) == ("unresolved", None, "NO_EXACT_MATCH")
    level = next(m.level for m in result.messages if m.code == "NO_EXACT_MATCH")
    assert level == "warning"


def test_slug_that_appears_in_the_catalog_becomes_exact_immediately(monkeypatch, env):
    tmp_path, _, _, _ = env
    _run(monkeypatch, env, _catalog(OK, f"~{REDIRECT}"))
    result = _run(monkeypatch, env, _catalog(OK, REDIRECT))
    assert result.not_tracked == []
    assert {p.model for p in result.prices_shortlist} == {OK, REDIRECT}
    assert _store(tmp_path)[REDIRECT]["identity"] == "exact"


def test_dry_run_does_not_persist_identity(monkeypatch, env):
    tmp_path, _, _, _ = env
    result = _run(monkeypatch, env, _catalog(OK, f"~{REDIRECT}"), dry_run=True)
    assert [m.identity for m in result.not_tracked] == ["redirect"]
    assert not (tmp_path / "effective_prices.json").exists()


def _seed_redirect_with_stale_history(tmp_path):
    (tmp_path / "effective_prices.json").write_text(json.dumps({
        REDIRECT: {"identity": "redirect", "resolved_id": f"~{REDIRECT}", "identity_checked": NOW.isoformat(),
                   "canonical_slug": "old/canonical", "last_synced": NOW.isoformat(),
                   "observations": [{"date": (NOW.date() - timedelta(days=n)).isoformat(),
                                     "effective_price_1m": 0.5} for n in range(0, 20)]},
        OK: {"identity": "exact", "resolved_id": OK, "canonical_slug": f"{OK}-1", "last_synced": NOW.isoformat(),
             "observations": [{"date": NOW.date().isoformat(), "effective_price_1m": 1.0}]},
    }), encoding="utf-8")


def test_local_reads_never_attribute_history_to_a_redirect(env):
    tmp_path, _, _, _ = env
    _seed_redirect_with_stale_history(tmp_path)
    for result in (read_check_result(no_hermes=True), read_history_result(no_hermes=True)):
        assert [p.model for p in result.prices_shortlist] == [OK]
        assert [(m.model, m.identity) for m in result.not_tracked] == [(REDIRECT, "redirect")]


def _cli_args():
    return argparse.Namespace(json=False, no_hermes=True, config=None, data_dir=None, hermes_config=None,
                              hints=False, model_id=None, csv=False, history_csv=False)


def test_human_json_and_mcp_output_show_not_tracked(env):
    tmp_path, _, _, _ = env
    _seed_redirect_with_stale_history(tmp_path)

    for command in (cmd_check, cmd_history):
        buf = io.StringIO()
        with redirect_stdout(buf):
            command(_cli_args())
        out = buf.getvalue()
        assert "NOT_TRACKED" in out and "redirect alias" in out and REDIRECT in out

    for tool in ("check_prices", "get_model_history"):
        payload = json.loads(asyncio.run(server.call_tool(tool, {})).content[0].text)
        [row] = payload["not_tracked"]
        assert row["status"] == "NOT_TRACKED" and row["model"] == REDIRECT
        assert row["identity"] == "redirect" and row["resolved_id"] == f"~{REDIRECT}"
        assert row["code"] == "REDIRECT_IDENTITY" and "diagnostic" in row
        assert [p["model"] for p in payload["prices_shortlist"]] == [OK]
