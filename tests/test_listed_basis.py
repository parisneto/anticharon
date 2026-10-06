"""Phase A (temporary side-by-side): listed prices blended by Anticharon, next to the
effective-price analytics. Expected values are derived by hand from the default
calibration 0.232622 / 0.764478 / 0.0029; nothing else in run/check/history changes."""

import argparse
import io
import json
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone

import pytest

from anticharon.cli import cmd_history
from anticharon.pricing import derive_listed_daily_prices
from anticharon.tracker import read_history_result, sync_effective_prices_for_model

W = (0.232622, 0.764478, 0.0029)
NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def steps(*points):
    return [{"at": at, "value": value} for at, value in points]


def endpoint(uuid, inputs, outputs, cache=None, slug="openai"):
    item = {"endpointId": uuid, "providerSlug": slug, "input": steps(*inputs), "output": steps(*outputs)}
    if cache is not None:
        item["cacheRead"] = steps(*cache)
    return item


def blend(p_in, p_cache, p_out):
    return p_in * W[0] + p_cache * W[1] + p_out * W[2]


def by_date(observations):
    return {o["date"]: o["effective_price_1m"] for o in observations}


def test_daily_value_uses_the_cheapest_standard_endpoint_and_the_end_of_day_step():
    # Standard endpoint cuts input 0.20 -> 0.10 at noon on 09-14; a flex endpoint is cheaper but excluded.
    std = endpoint("std", [("2026-09-01T00:00:00Z", 0.20), ("2026-09-14T12:00:00Z", 0.10)],
                   [("2026-09-01T00:00:00Z", 1.20)], [("2026-09-01T00:00:00Z", 0.02)])
    flex = endpoint("flex", [("2026-09-01T00:00:00Z", 0.05)], [("2026-09-01T00:00:00Z", 0.30)],
                    [("2026-09-01T00:00:00Z", 0.005)])

    out = by_date(derive_listed_daily_prices([std, flex], frozenset({"flex"}), W, TODAY, NOW))

    assert out["2026-09-13"] == pytest.approx(blend(0.20, 0.02, 1.20))  # 0.06529396
    assert out["2026-09-14"] == pytest.approx(blend(0.10, 0.02, 1.20))  # end-of-day value after the noon cut
    assert out["2026-09-16"] == pytest.approx(blend(0.10, 0.02, 1.20))  # today, at `now`
    with_flex = by_date(derive_listed_daily_prices([std, flex], frozenset(), W, TODAY, NOW))
    assert with_flex["2026-09-13"] == pytest.approx(blend(0.05, 0.005, 0.30))  # what the old rule would give


def test_endpoint_added_mid_window_is_skipped_before_it_exists_and_missing_cache_is_ten_percent():
    old = endpoint("old", [("2026-08-20T00:00:00Z", 0.30)], [("2026-08-20T00:00:00Z", 1.0)])  # no cacheRead
    new = endpoint("new", [("2026-09-10T08:00:00Z", 0.10)], [("2026-09-10T08:00:00Z", 1.0)],
                   [("2026-09-10T08:00:00Z", 0.01)])

    out = by_date(derive_listed_daily_prices([old, new], frozenset(), W, TODAY, NOW))

    assert out["2026-09-09"] == pytest.approx(blend(0.30, 0.03, 1.0))  # 10% cache fallback, new endpoint absent
    assert out["2026-09-10"] == pytest.approx(blend(0.10, 0.01, 1.0))  # new endpoint exists by end of day


def test_days_before_any_point_have_no_value():
    only = endpoint("a", [("2026-09-12T00:00:00Z", 0.2)], [("2026-09-12T00:00:00Z", 1.2)], [("2026-09-12T00:00:00Z", 0.02)])
    out = by_date(derive_listed_daily_prices([only], frozenset(), W, TODAY, NOW))
    assert min(out) == "2026-09-12" and "2026-09-11" not in out


def test_sync_stores_listed_series_and_blend_next_to_the_effective_observations(monkeypatch):
    std = endpoint("std-uuid", [("2026-09-01T00:00:00Z", 0.20)], [("2026-09-01T00:00:00Z", 1.20)],
                   [("2026-09-01T00:00:00Z", 0.02)])
    flex = endpoint("flex-uuid", [("2026-09-01T00:00:00Z", 0.10)], [("2026-09-01T00:00:00Z", 0.60)],
                    [("2026-09-01T00:00:00Z", 0.01)])
    effective = {"inputChartData": [{"x": "2026-09-15 00:00:00", "y": {"std-uuid": 0.09, "flex-uuid": 0.04}}],
                 "outputChartData": [{"x": "2026-09-15 00:00:00", "y": {"std-uuid": 1.2, "flex-uuid": 0.6}}]}
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **k: effective)
    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: {"series": [std, flex]})
    endpoints = [{"tag": "openai", "pricing": {"prompt": "2e-7", "completion": "1.2e-6"}},
                 {"tag": "openai/flex", "pricing": {"prompt": "1e-7", "completion": "6e-7"}}]
    store = {}

    sync_effective_prices_for_model("m/x", "m/x-1", store, W[2], 5.0, now=NOW, endpoints=endpoints, weights=W)

    entry = store["m/x"]
    assert by_date(entry["observations"]) == {"2026-09-15": pytest.approx(0.09 * (1 - W[2]) + 1.2 * W[2])}
    assert by_date(entry["listed_blend"])["2026-09-15"] == pytest.approx(blend(0.20, 0.02, 1.20))
    assert entry["listed_weights"] == list(W)
    assert {item["endpointId"] for item in entry["listed"]} == {"std-uuid", "flex-uuid"}


def test_sync_without_weights_stores_no_listed_blend(monkeypatch):
    monkeypatch.setattr("anticharon.tracker.fetch_effective_pricing_history", lambda *a, **k: {})
    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: {"series": []})
    store = {}
    sync_effective_prices_for_model("m/x", "m/x-1", store, W[2], 5.0, now=NOW)
    assert "listed_blend" not in store["m/x"]


@pytest.fixture
def history_env(monkeypatch, tmp_path):
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": "m/x", "source": "manual"}, {"model": "m/y", "source": "manual"}]}),
                   encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("anticharon.tracker.datetime", _Clock)
    effective = [{"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": 0.05 + 0.01 * (n % 3)}
                 for n in range(20)]
    listed_blend = [{"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": 0.0653} for n in range(20)]
    store = {"m/x": {"canonical_slug": "m/x-1", "last_synced": NOW.isoformat(), "observations": effective,
                     "listed_blend": listed_blend},
             "m/y": {"canonical_slug": "m/y-1", "last_synced": NOW.isoformat(), "observations": effective}}
    (tmp_path / "effective_prices.json").write_text(json.dumps(store), encoding="utf-8")
    return tmp_path


def test_history_json_and_human_output_show_the_listed_basis_beside_the_current_analytics(history_env):
    result = read_history_result(no_hermes=True)
    rows = {p.model: p for p in result.prices_shortlist}

    basis = rows["m/x"].to_dict()["listed_basis"]
    assert basis["basis"] == "listed_blend" and basis["latest_1m"] == 0.0653
    assert basis["volatility_cv_pct"] == 0.0 and basis["profile"] == "STABLE" and basis["observation_count"] == 20
    assert rows["m/x"].analytics.volatility_cv_pct > 0  # the effective-based analytics are unchanged
    assert "listed_basis" not in rows["m/y"].to_dict()  # no stored listed series -> no comparison

    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_history(argparse.Namespace(json=False, no_hermes=True, config=None, data_dir=None, hermes_config=None,
                                       hints=False, model_id=None, csv=False, history_csv=False))
    out = buf.getvalue()
    assert "listed basis (temporary comparison): $0.06530 STABLE, CV 0.0%" in out
    assert out.count("listed basis (temporary comparison)") == 1
