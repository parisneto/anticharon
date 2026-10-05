"""Independent-review fixes: quote/observation basis, alert persistence after an
all-reuse run, no identity change from an empty catalog, and same-day reuse of a
redirect slug."""

import argparse
import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import pytest

from anticharon.cli import cmd_check
from anticharon.storage import write_history
from anticharon.tracker import read_check_result, read_history_result, run_tracker

A, B = "acme/model-a", "acme/other-b"
NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def _catalog(prices):
    return {m: {"id": m, "canonical_slug": f"{m}-1", "pricing": {"prompt": p, "completion": c}}
            for m, (p, c) in prices.items()}


CATALOG = _catalog({A: ("0.000002", "0.00001"), B: ("0.000003", "0.00002")})


@pytest.fixture
def env(monkeypatch, tmp_path):
    cfg = tmp_path / "shortlist.json"
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("anticharon.tracker.datetime", _Clock)
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **k: [])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **k: {})
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: CATALOG)
    return tmp_path, cfg


def _write_cfg(cfg, default):
    cfg.write_text(json.dumps({"shortlist": [
        {"model": m, "source": "manual", **({"order": 0} if m == default else {})} for m in (A, B)]}),
        encoding="utf-8")


def _seed_store(tmp_path, slugs, price=1.0, **extra):
    (tmp_path / "effective_prices.json").write_text(json.dumps({
        m: {"canonical_slug": f"{m}-1", "first_seen": TODAY.isoformat(), "last_synced": NOW.isoformat(),
            "identity": "exact", "resolved_id": m, "identity_checked": NOW.isoformat(),
            "observations": [{"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": price}
                             for n in range(14)], **extra}
        for m in slugs}), encoding="utf-8")


def _alerts(tmp_path):
    return json.loads((tmp_path / "alerts.json").read_text(encoding="utf-8"))


def test_quote_is_shown_beside_the_observation_and_alerts_state_their_basis(env):
    tmp_path, cfg = env
    _write_cfg(cfg, A)
    _seed_store(tmp_path, [A, B])  # observations 1.0
    write_history([[m, NOW.isoformat(), 2.6, 2.6, 2.6, 2.6, 2.6] + [None] * 9 for m in (A, B)],
                  tmp_path / "history.csv")

    for result in (read_check_result(no_hermes=True), read_history_result(no_hermes=True)):
        row = result.prices_shortlist[0]
        assert (row.price_1m, row.price_source) == (1.0, "observation")
        assert (row.quote_1m, row.quote_date) == (2.6, TODAY.isoformat())
        assert row.to_dict()["last_run_quote_1m"] == 2.6

    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_check(argparse.Namespace(json=False, no_hermes=True, config=None, data_dir=None,
                                     hermes_config=None, hints=False, model_id=None, history_csv=False))
    assert "last run quote: $2.60000/1M" in buf.getvalue()

    run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True, force=True)
    messages = [w["message"] for w in _alerts(tmp_path)["price_warnings"] if w["type"] in ("PRICE_SPIKE", "PRICE_DROP")]
    assert all("observed average" in m and "Current quote" in m for m in messages)


def test_all_reuse_run_still_persists_the_current_default(env):
    tmp_path, cfg = env
    _write_cfg(cfg, A)
    run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True)
    assert _alerts(tmp_path)["default_model"] == A

    _write_cfg(cfg, B)  # default changes; every model is reused under the same-day rule
    result = run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True)

    assert {p.price_source for p in result.prices_shortlist} == {"cached_quote"}
    assert _alerts(tmp_path)["default_model"] == B
    assert [p.model for p in read_check_result(no_hermes=True).prices_shortlist if p.is_default] == [B]


def test_empty_catalog_never_reclassifies_identity_or_hides_stored_history(env, monkeypatch):
    tmp_path, cfg = env
    _write_cfg(cfg, A)
    _seed_store(tmp_path, [A, B])
    before = (tmp_path / "effective_prices.json").read_bytes()
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {})
    assert not (tmp_path / "history.csv").exists()

    result = run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True)

    assert result.not_tracked == []
    assert "CATALOG_UNAVAILABLE" in [m.code for m in result.messages]
    assert "NO_EXACT_MATCH" not in [m.code for m in result.messages]
    assert (tmp_path / "effective_prices.json").read_bytes() == before
    local = read_check_result(no_hermes=True)
    assert {p.model for p in local.prices_shortlist} == {A, B} and local.not_tracked == []


def test_same_day_reuse_never_shows_a_redirect_as_priced(env, monkeypatch):
    tmp_path, cfg = env
    _write_cfg(cfg, A)
    run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True)
    store = json.loads((tmp_path / "effective_prices.json").read_text(encoding="utf-8"))
    store[B].update({"identity": "redirect", "resolved_id": f"~{B}", "identity_checked": NOW.isoformat()})
    (tmp_path / "effective_prices.json").write_text(json.dumps(store), encoding="utf-8")
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models",
                        lambda timeout=10.0: _catalog({A: ("0.000002", "0.00001"), f"~{B}": ("0.000003", "0.00002")}))

    result = run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True)

    assert [p.model for p in result.prices_shortlist] == [A]
    assert [(m.model, m.identity) for m in result.not_tracked] == [(B, "redirect")]
