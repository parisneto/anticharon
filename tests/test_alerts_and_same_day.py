"""W3 (MCP-10, MCP-11, D-18/D-18b/D-18c/D-19/D-22/D-28): the same-day rule,
alerts.json persistence, and the check/history <-> run network split.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from anticharon.storage import get_alerts_path, read_alerts, read_history
from anticharon.tracker import read_check_result, read_history_result, run_tracker


def _write_shortlist(tmp_path: Path, entries: list) -> Path:
    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({
        "shortlist": entries,
        "weight_uncached_prompt": 0.232622,
        "weight_cached_prompt": 0.764478,
        "weight_completion": 0.0029,
    }), encoding="utf-8")
    return cfg_path


@pytest.fixture
def two_model_catalog(monkeypatch):
    calls = {"count": 0}

    def fake_endpoints(canonical_slug, timeout=10.0):
        calls["count"] += 1
        return []

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "p/alpha": {"id": "p/alpha", "canonical_slug": "p/alpha", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
        "p/beta": {"id": "p/beta", "canonical_slug": "p/beta", "pricing": {"prompt": "0.000005", "completion": "0.00001"}},
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", fake_endpoints)
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})
    return calls


def test_same_day_rerun_skips_per_model_fetch_unless_forced(tmp_path, two_model_catalog):
    cfg_path = _write_shortlist(tmp_path, ["p/alpha", "p/beta"])
    hist_path = tmp_path / "history.csv"

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)
    assert two_model_catalog["count"] == 2  # one endpoint fetch per model

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)
    assert two_model_catalog["count"] == 2  # same-day rerun: no new per-model fetch (MCP-10)

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True, force=True)
    assert two_model_catalog["count"] == 4  # --force bypasses the same-day rule (D-3)


def test_run_model_filter_never_drops_other_models_history(tmp_path, two_model_catalog):
    """Regression: a filtered `run --model` used to rewrite history.csv with
    only that one model's row, silently discarding every other shortlisted
    model's history (MCP-10 acceptance: no shortlisted model ever dropped)."""
    cfg_path = _write_shortlist(tmp_path, ["p/alpha", "p/beta"])
    hist_path = tmp_path / "history.csv"

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)
    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True, model_id="p/alpha", force=True)

    history = read_history(hist_path)
    assert set(history) == {"p/alpha", "p/beta"}


def test_run_persists_alerts_json_and_check_reads_it_verbatim(tmp_path, two_model_catalog, monkeypatch):
    cfg_path = _write_shortlist(tmp_path, [
        {"model": "p/alpha", "source": "manual", "order": 0},
        {"model": "p/beta", "source": "manual"},
    ])
    hist_path = tmp_path / "history.csv"

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)

    alerts = read_alerts(get_alerts_path(hist_path.parent))
    assert alerts["default_model"] == "p/alpha"
    assert alerts["data_source"] == "live_api"
    assert "price_warnings" in alerts

    # check_prices/check must never touch the network, and must read this
    # alerts.json verbatim rather than recomputing anything (D-19/D-22).
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models",
                         lambda **kw: (_ for _ in ()).throw(AssertionError("check must not fetch")))
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing",
                         lambda **kw: (_ for _ in ()).throw(AssertionError("check must not fetch")))
    res = read_check_result(config_path=cfg_path, history_path=hist_path, no_hermes=True)
    assert res.status == "success"
    assert [w.to_dict() for w in res.price_warnings] == alerts["price_warnings"]


def test_run_model_filter_replaces_only_target_alerts_and_recomputes_cross_model(tmp_path, monkeypatch):
    """D-22 Rule 1: `run --model X` replaces X's per-model alerts and
    recomputes the cross-model BEST_OPTION_CHANGED alert from all stored
    prices, but leaves every other model's persisted alert untouched."""
    cfg_path = _write_shortlist(tmp_path, [
        {"model": "p/default", "source": "manual", "order": 0},
        {"model": "p/other", "source": "manual"},
    ])
    hist_path = tmp_path / "history.csv"

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "p/default": {"id": "p/default", "canonical_slug": "p/default", "pricing": {"prompt": "0.000010", "completion": "0.00002"}},
        "p/other": {"id": "p/other", "canonical_slug": "p/other", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
    })
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **kw: [])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **kw: {})

    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True)
    alerts_path = get_alerts_path(hist_path.parent)
    first = read_alerts(alerts_path)
    best_option = [w for w in first["price_warnings"] if w["type"] == "BEST_OPTION_CHANGED"]
    assert best_option and best_option[0]["suggested_cheapest"] == "p/other"
    default_price_before = read_history(hist_path)["p/default"].effective_price_1m

    # Re-fetch only p/other, now priced even lower -- the cross-model alert
    # must be recomputed (still pointing at p/other), and p/default's own
    # persisted state must be unaffected by this filtered run.
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "p/other": {"id": "p/other", "canonical_slug": "p/other", "pricing": {"prompt": "0.0000001", "completion": "0.0000002"}},
    })
    run_tracker(dry_run=False, config_path=cfg_path, history_path=hist_path, no_hermes=True, model_id="p/other", force=True)

    second = read_alerts(alerts_path)
    best_option_2 = [w for w in second["price_warnings"] if w["type"] == "BEST_OPTION_CHANGED"]
    assert len(best_option_2) == 1
    assert best_option_2[0]["suggested_cheapest"] == "p/other"

    history = read_history(hist_path)
    assert history["p/default"].effective_price_1m == pytest.approx(default_price_before)


def test_check_and_history_make_zero_network_calls(tmp_path, monkeypatch):
    """MCP-11 acceptance: check/check_prices and history/get_model_history
    make zero network calls, even with a live-looking shortlist and history."""
    cfg_path = _write_shortlist(tmp_path, ["p/alpha"])
    hist_path = tmp_path / "history.csv"
    hist_path.write_text(
        "model,last_updated,effective_price_1m,advertised_prompt_1m,advertised_completion_1m,ma_3d,ma_7d,"
        "d1,d2,d3,d4,d5,d6,d7,d15,d30\n"
        f"p/alpha,{datetime.now(timezone.utc).isoformat()},1.0,0.5,2.0,1.0,1.0,,,,,,,,,\n",
        encoding="utf-8",
    )

    def _boom(*a, **kw):
        raise AssertionError("network was called")

    monkeypatch.setattr("anticharon.tracker.requests.get", _boom)
    monkeypatch.setattr("anticharon.hermes.get_hermes_models", lambda **kw: None)

    check_res = read_check_result(config_path=cfg_path, history_path=hist_path, hermes_config_path=None)
    assert check_res.status == "success"

    history_res = read_history_result(config_path=cfg_path, history_path=hist_path, hermes_config_path=None)
    assert history_res.status == "success"


def test_check_model_filter_reports_not_monitored_without_network(tmp_path, monkeypatch):
    """D-1 §3d: a local read's absent-slug result is `not_monitored` (a normal
    result, not an error) -- `refused`/isError is reserved for a filtered
    *live* run (`run --model`)."""
    cfg_path = _write_shortlist(tmp_path, ["p/alpha"])
    hist_path = tmp_path / "history.csv"

    def _boom(*a, **kw):
        raise AssertionError("network was called")

    monkeypatch.setattr("anticharon.tracker.requests.get", _boom)
    res = read_check_result(config_path=cfg_path, history_path=hist_path, no_hermes=True, model_id="p/not-there")
    assert res.status == "not_monitored"
    assert res.messages[0].code == "NOT_MONITORED"
    assert res.messages[0].level == "warning"
