"""Track 2 (release gate): PRICE_SPIKE/PRICE_DROP compare observed prices with the
observed history. The live quote never raises one; its gap to the latest observation
is the separate `quote_vs_observed_pct` field. Live response and persisted alerts agree."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from anticharon.tracker import read_check_result, run_tracker

MODEL = "acme/model"
NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


@pytest.fixture
def env(monkeypatch, tmp_path):
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": MODEL, "source": "manual", "order": 0}]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("anticharon.tracker.datetime", _Clock)
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **k: [])
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history",
                        lambda *a, **k: pytest.fail("a fresh store must not refetch"))
    return tmp_path, cfg


def _catalog(monkeypatch, prompt):
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        MODEL: {"id": MODEL, "canonical_slug": f"{MODEL}-1", "pricing": {"prompt": prompt, "completion": "0"}}})


def _seed(tmp_path, today_price, past_price=1.0, days=14):
    """Observations: `past_price` for the 14 previous days, `today_price` today."""
    observations = [{"date": TODAY.isoformat(), "effective_price_1m": today_price}] if today_price is not None else []
    observations += [{"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": past_price}
                     for n in range(1, days + 1)]
    (tmp_path / "effective_prices.json").write_text(json.dumps({MODEL: {
        "canonical_slug": f"{MODEL}-1", "first_seen": TODAY.isoformat(), "last_synced": NOW.isoformat(),
        "identity": "exact", "resolved_id": MODEL, "identity_checked": NOW.isoformat(),
        "observations": observations}}), encoding="utf-8")


def _run(tmp_path, cfg):
    return run_tracker(config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True, force=True)


def _moves(warnings):
    return {w.type: w.message for w in warnings if w.type in ("PRICE_SPIKE", "PRICE_DROP")}


def _persisted_moves(tmp_path):
    alerts = json.loads((tmp_path / "alerts.json").read_text(encoding="utf-8"))["price_warnings"]
    return {w["type"]: w["message"] for w in alerts if w["type"] in ("PRICE_SPIKE", "PRICE_DROP")}


def test_flat_observations_with_a_far_quote_raise_no_spike_and_report_the_gap(env, monkeypatch):
    tmp_path, cfg = env
    _seed(tmp_path, today_price=1.0)
    _catalog(monkeypatch, "0.0000084116")  # blended quote about 2.6 per 1M (10% cache fallback)

    result = _run(tmp_path, cfg)

    row = result.prices_shortlist[0]
    assert 2.55 < row.price_1m < 2.65
    assert row.change_vs_7d_pct == pytest.approx(0.0)
    assert row.quote_vs_observed_pct == pytest.approx((row.price_1m - 1.0) * 100, abs=1e-6)
    assert 155 < row.to_dict()["quote_vs_observed_pct"] < 165
    assert _moves(result.price_warnings) == {} and _persisted_moves(tmp_path) == {}


def test_observed_jump_raises_a_spike_even_when_the_quote_is_flat(env, monkeypatch):
    tmp_path, cfg = env
    _seed(tmp_path, today_price=1.5)  # +50% vs the 7-day observed average of 1.0
    _catalog(monkeypatch, "0.0000032350")  # quote about 1.0, equal to the old average

    result = _run(tmp_path, cfg)

    moves = _moves(result.price_warnings)
    assert list(moves) == ["PRICE_SPIKE"]
    assert "+50.0%" in moves["PRICE_SPIKE"] and "observed average" in moves["PRICE_SPIKE"]
    assert _persisted_moves(tmp_path) == moves  # the live response equals alerts.json


def test_observed_fall_raises_a_drop(env, monkeypatch):
    tmp_path, cfg = env
    _seed(tmp_path, today_price=0.5)
    _catalog(monkeypatch, "0.0000032350")

    moves = _moves(_run(tmp_path, cfg).price_warnings)

    assert list(moves) == ["PRICE_DROP"] and "50.0%" in moves["PRICE_DROP"]
    assert _persisted_moves(tmp_path) == moves


def test_no_observations_means_no_alert(env, monkeypatch):
    tmp_path, cfg = env
    (tmp_path / "effective_prices.json").write_text(json.dumps({MODEL: {
        "canonical_slug": f"{MODEL}-1", "first_seen": TODAY.isoformat(), "last_synced": NOW.isoformat(),
        "observations": []}}), encoding="utf-8")
    _catalog(monkeypatch, "0.0000084116")

    result = _run(tmp_path, cfg)

    assert result.prices_shortlist[0].quote_vs_observed_pct is None
    assert _moves(result.price_warnings) == {} and _persisted_moves(tmp_path) == {}


def test_check_after_run_reports_the_same_alerts_as_the_run(env, monkeypatch):
    tmp_path, cfg = env
    _seed(tmp_path, today_price=1.5)
    _catalog(monkeypatch, "0.0000032350")
    live = _moves(_run(tmp_path, cfg).price_warnings)

    assert _moves(read_check_result(no_hermes=True).price_warnings) == live
