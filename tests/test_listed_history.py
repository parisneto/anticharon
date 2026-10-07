"""History on the listed-price basis (D-10): OpenRouter's listed endpoint prices blended with
the calibration, standard tiers only. Expected values are derived by hand from the default
calibration 0.232622 / 0.764478 / 0.0029."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from anticharon.pricing import derive_listed_daily_prices
from anticharon.tracker import (
    read_history_result,
    stored_observations,
    sync_effective_prices_for_model,
    upsert_today_observation,
)

W = (0.232622, 0.764478, 0.0029)
NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
TODAY = NOW.date()
FIXTURES = Path(__file__).parent / "fixtures"


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


def endpoints_for(*tags_prices):
    return [{"tag": tag, "pricing": {"prompt": str(i / 1e6), "completion": str(o / 1e6)}} for tag, i, o in tags_prices]


def test_a_day_is_the_time_weighted_mean_of_the_cheapest_standard_price():
    # Standard endpoint cuts input 0.20 -> 0.10 at noon on 09-14; a flex endpoint is cheaper but excluded.
    std = endpoint("std", [("2026-09-01T00:00:00Z", 0.20), ("2026-09-14T12:00:00Z", 0.10)],
                   [("2026-09-01T00:00:00Z", 1.20)], [("2026-09-01T00:00:00Z", 0.02)])
    flex = endpoint("flex", [("2026-09-01T00:00:00Z", 0.05)], [("2026-09-01T00:00:00Z", 0.30)],
                    [("2026-09-01T00:00:00Z", 0.005)])

    out = by_date(derive_listed_daily_prices([std, flex], frozenset({"std"}), W, TODAY, NOW))

    before, after = blend(0.20, 0.02, 1.20), blend(0.10, 0.02, 1.20)  # 0.06529396, 0.04200...
    assert out["2026-09-13"] == pytest.approx(before)
    assert out["2026-09-14"] == pytest.approx((before + after) / 2)  # 12 h at each price
    assert out["2026-09-15"] == pytest.approx(after)
    assert out["2026-09-16"] == pytest.approx(after)  # today: the price at `now`
    with_flex = by_date(derive_listed_daily_prices([std, flex], frozenset({"std", "flex"}), W, TODAY, NOW))
    assert with_flex["2026-09-13"] == pytest.approx(blend(0.05, 0.005, 0.30))  # the old, tier-mixed rule


def test_the_cheapest_endpoint_is_taken_at_each_moment_not_per_day():
    # A cuts input 0.20 -> 0.05 at 06:00 on 09-14; B stays at 0.10. B is cheapest for 6 h, A for 18 h.
    a = endpoint("a", [("2026-09-01T00:00:00Z", 0.20), ("2026-09-14T06:00:00Z", 0.05)], [("2026-09-01T00:00:00Z", 1.0)])
    b = endpoint("b", [("2026-09-01T00:00:00Z", 0.10)], [("2026-09-01T00:00:00Z", 1.0)])  # no cacheRead: 10% of input

    out = by_date(derive_listed_daily_prices([a, b], frozenset({"a", "b"}), W, TODAY, NOW))

    expected = (blend(0.10, 0.01, 1.0) * 6 + blend(0.05, 0.005, 1.0) * 18) / 24
    assert out["2026-09-14"] == pytest.approx(expected)


def test_a_brief_dip_at_the_end_of_a_day_does_not_become_the_days_price():
    # Price 0.0107 until 23:50, then a 10-minute dip to 0.00374: the day is ~0.0107, not 0.00374.
    dip = endpoint("d", [("2026-09-01T00:00:00Z", 0.0107), ("2026-09-14T23:50:00Z", 0.00374)],
                   [("2026-09-01T00:00:00Z", 0.5)], [("2026-09-01T00:00:00Z", 0.001)])

    out = by_date(derive_listed_daily_prices([dip], frozenset({"d"}), W, TODAY, NOW))

    high, low = blend(0.0107, 0.001, 0.5), blend(0.00374, 0.001, 0.5)
    assert out["2026-09-14"] == pytest.approx((high * (23 * 60 + 50) + low * 10) / (24 * 60))
    assert out["2026-09-14"] > 0.99 * high


def test_endpoint_added_mid_day_counts_only_from_when_it_exists_and_missing_cache_is_ten_percent():
    old = endpoint("old", [("2026-08-20T00:00:00Z", 0.30)], [("2026-08-20T00:00:00Z", 1.0)])  # no cacheRead
    new = endpoint("new", [("2026-09-10T08:00:00Z", 0.10)], [("2026-09-10T08:00:00Z", 1.0)],
                   [("2026-09-10T08:00:00Z", 0.01)])

    out = by_date(derive_listed_daily_prices([old, new], frozenset({"old", "new"}), W, TODAY, NOW))

    assert out["2026-09-09"] == pytest.approx(blend(0.30, 0.03, 1.0))  # 10% cache fallback, new endpoint absent
    assert out["2026-09-10"] == pytest.approx((blend(0.30, 0.03, 1.0) * 8 + blend(0.10, 0.01, 1.0) * 16) / 24)
    assert out["2026-09-11"] == pytest.approx(blend(0.10, 0.01, 1.0))


def test_time_before_any_endpoint_exists_is_left_out_of_the_mean():
    late = endpoint("late", [("2026-09-12T18:00:00Z", 0.2)], [("2026-09-12T18:00:00Z", 1.2)], [("2026-09-12T18:00:00Z", 0.02)])
    out = by_date(derive_listed_daily_prices([late], frozenset({"late"}), W, TODAY, NOW))
    assert out["2026-09-12"] == pytest.approx(blend(0.2, 0.02, 1.2))  # only the 6 h it existed, not diluted
    assert "2026-09-11" not in out


def test_days_before_any_point_have_no_value():
    only = endpoint("a", [("2026-09-12T00:00:00Z", 0.2)], [("2026-09-12T00:00:00Z", 1.2)], [("2026-09-12T00:00:00Z", 0.02)])
    out = by_date(derive_listed_daily_prices([only], frozenset({"a"}), W, TODAY, NOW))
    assert min(out) == "2026-09-12" and "2026-09-11" not in out


def _sync(store, listed, *, weights=W, now=NOW, force=False, endpoints=None, model="m/x"):
    from anticharon import tracker

    tracker.fetch_listed_pricing = lambda *a, **k: listed
    sync_effective_prices_for_model(model, f"{model}-1", store, weights, 5.0, now=now, force=force,
                                    endpoints=endpoints if endpoints is not None else endpoints_for(("openai", 0.2, 1.2)))


@pytest.fixture(autouse=True)
def restore_fetch(monkeypatch):
    from anticharon import tracker

    monkeypatch.setattr(tracker, "fetch_listed_pricing", tracker.fetch_listed_pricing)


STD = endpoint("std-uuid", [("2026-09-01T00:00:00Z", 0.20)], [("2026-09-01T00:00:00Z", 1.20)], [("2026-09-01T00:00:00Z", 0.02)])


def test_day_zero_backfill_gives_a_mature_history_from_the_real_listed_fixture():
    listed = json.loads((FIXTURES / "openrouter_listed_pricing_gpt-5.6-luna_trimmed.json").read_text(encoding="utf-8"))["data"]
    endpoints = [{"tag": t, "pricing": {"prompt": str(i / 1e6), "completion": str(o / 1e6)}}
                 for t, i, o in [("openai/flex", 0.1, 0.6), ("azure", 0.2, 1.2), ("openai", 0.2, 1.2),
                                 ("azure/eu", 0.22, 1.32), ("amazon-bedrock/us-east-1", 0.22, 1.32), ("openai/fast", 0.4, 2.4)]]
    store = {}
    _sync(store, listed, endpoints=endpoints, model="openai/gpt-5.6-luna", now=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc))

    observations = store["openai/gpt-5.6-luna"]["observations"]
    assert len(observations) == 31 and observations[0]["date"] == "2026-09-06"  # a full 30-day window on the very first run
    assert all(o["effective_price_1m"] == pytest.approx(blend(0.2, 0.02, 1.2)) for o in observations)


def test_recalibration_rederives_stored_history_without_a_refetch():
    store = {}
    _sync(store, {"series": [STD]})
    before = store["m/x"]["observations"][-1]["effective_price_1m"]
    assert before == pytest.approx(blend(0.2, 0.02, 1.2))

    from anticharon import tracker
    tracker.fetch_listed_pricing = lambda *a, **k: pytest.fail("a fresh entry must not refetch on recalibration")
    new_weights = (0.5, 0.4968, 0.0032)
    sync_effective_prices_for_model("m/x", "m/x-1", store, new_weights, 5.0, now=NOW + timedelta(hours=1),
                                    endpoints=endpoints_for(("openai", 0.2, 1.2)))

    assert store["m/x"]["weights_used"] == list(new_weights)
    assert store["m/x"]["observations"][-1]["effective_price_1m"] == pytest.approx(
        0.2 * 0.5 + 0.02 * 0.4968 + 1.2 * 0.0032)


def test_stale_entry_refetches_fresh_does_not_and_force_does():
    calls = []
    from anticharon import tracker

    tracker.fetch_listed_pricing = lambda *a, **k: calls.append(1) or {"series": [STD]}
    store = {}
    kwargs = {"endpoints": endpoints_for(("openai", 0.2, 1.2))}
    sync_effective_prices_for_model("m/x", "m/x-1", store, W, 5.0, now=NOW, **kwargs)
    sync_effective_prices_for_model("m/x", "m/x-1", store, W, 5.0, now=NOW + timedelta(hours=2), **kwargs)
    assert len(calls) == 1
    sync_effective_prices_for_model("m/x", "m/x-1", store, W, 5.0, now=NOW + timedelta(hours=3), force=True, **kwargs)
    assert len(calls) == 2
    sync_effective_prices_for_model("m/x", "m/x-1", store, W, 5.0, now=NOW + timedelta(hours=30), **kwargs)
    assert len(calls) == 3


def test_failed_fetch_keeps_previous_history_and_a_router_alias_gets_none():
    store = {}
    _sync(store, {"series": [STD]})
    kept = list(store["m/x"]["observations"])
    _sync(store, {}, force=True)
    assert store["m/x"]["observations"] == kept  # a transient failure never destroys stored history

    alias = {}
    _sync(alias, {}, model="~deepseek/deepseek-pro-latest")
    assert alias["~deepseek/deepseek-pro-latest"].get("observations", []) == []
    assert alias["~deepseek/deepseek-pro-latest"]["first_seen"] == TODAY.isoformat()


def test_legacy_effective_history_is_kept_aside_never_read_and_replaced_on_first_refresh():
    legacy_obs = [{"date": "2026-09-15", "effective_price_1m": 0.09}]
    legacy = {"m/x": {"canonical_slug": "m/x-1", "first_seen": "2026-08-01", "last_synced": NOW.isoformat(),
                      "observations": legacy_obs}}  # no `basis` marker, fresh: the old effective series
    assert stored_observations(legacy["m/x"]) == []  # never mixed with the new basis

    _sync(legacy, {"series": [STD]})  # a fresh legacy entry is still upgraded immediately

    entry = legacy["m/x"]
    assert entry["legacy_effective_observations"] == legacy_obs
    assert entry["basis"] == "listed_blend" and entry["observations"][-1]["effective_price_1m"] == pytest.approx(blend(0.2, 0.02, 1.2))
    assert entry["first_seen"] == "2026-08-01"

    failed = {"m/x": {"canonical_slug": "m/x-1", "last_synced": NOW.isoformat(), "observations": legacy_obs}}
    _sync(failed, {})  # upgrade fetch fails: nothing mixed, legacy kept aside, retried next run
    assert failed["m/x"]["observations"] == [] and failed["m/x"]["legacy_effective_observations"] == legacy_obs
    assert stored_observations(failed["m/x"]) == []


def test_upsert_today_replaces_todays_point_only_on_the_listed_basis():
    entry = {"basis": "listed_blend", "observations": [{"date": "2026-09-15", "effective_price_1m": 0.1},
                                                         {"date": "2026-09-16", "effective_price_1m": 0.2}]}
    upsert_today_observation(entry, TODAY, 0.3)
    assert by_date(entry["observations"]) == {"2026-09-15": 0.1, "2026-09-16": 0.3}

    legacy = {"observations": [{"date": "2026-09-15", "effective_price_1m": 0.1}]}
    upsert_today_observation(legacy, TODAY, 0.3)
    assert legacy["observations"] == [{"date": "2026-09-15", "effective_price_1m": 0.1}]


def test_local_reads_of_a_legacy_only_store_use_the_cached_quote_and_report_no_history(monkeypatch, tmp_path):
    from anticharon.storage import write_history

    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": "m/x", "source": "manual"}]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("anticharon.tracker.datetime", _Clock)
    (tmp_path / "effective_prices.json").write_text(json.dumps({"m/x": {
        "canonical_slug": "m/x-1", "last_synced": NOW.isoformat(),
        "observations": [{"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": 0.5} for n in range(20)]}}),
        encoding="utf-8")
    write_history([["m/x", NOW.isoformat(), 0.7, 0.2, 1.2, 0.7, 0.7] + [None] * 9], tmp_path / "history.csv")

    row = read_history_result(no_hermes=True).prices_shortlist[0]

    assert (row.price_1m, row.price_source) == (0.7, "cached_quote")
    assert row.analytics.profile == "NEWLY_TRACKED" and row.analytics.observation_count == 0


# --- second independent review: invalid steps, same-day recalibration, partial outage, malformed series ---

def test_invalid_listed_steps_never_displace_a_valid_endpoints_price():
    valid = endpoint("ok", [("2026-09-01T00:00:00Z", 0.20)], [("2026-09-01T00:00:00Z", 1.20)], [("2026-09-01T00:00:00Z", 0.02)])
    negative = endpoint("neg", [("2026-09-01T00:00:00Z", -1.0)], [("2026-09-01T00:00:00Z", 1.0)])
    not_a_number = endpoint("nan", [("2026-09-01T00:00:00Z", float("nan"))], [("2026-09-01T00:00:00Z", 1.0)])
    infinite = endpoint("inf", [("2026-09-01T00:00:00Z", float("inf"))], [("2026-09-01T00:00:00Z", 0.0)])

    out = derive_listed_daily_prices([valid, negative, not_a_number, infinite],
                                     frozenset({"ok", "neg", "nan", "inf"}), W, TODAY, NOW)

    assert out and all(o["effective_price_1m"] == pytest.approx(blend(0.20, 0.02, 1.20)) for o in out)


def test_an_invalid_step_keeps_the_previous_valid_step_in_effect():
    cut_then_bad = endpoint("a", [("2026-09-01T00:00:00Z", 0.20), ("2026-09-10T00:00:00Z", -1.0)],
                            [("2026-09-01T00:00:00Z", 1.20)], [("2026-09-01T00:00:00Z", 0.02)])
    out = by_date(derive_listed_daily_prices([cut_then_bad], frozenset({"a"}), W, TODAY, NOW))
    assert out["2026-09-12"] == pytest.approx(blend(0.20, 0.02, 1.20))


def test_malformed_nested_series_degrades_to_no_history_instead_of_crashing(monkeypatch):
    from anticharon import tracker

    class Response:
        def raise_for_status(self):
            pass

        def __init__(self, payload):
            self.payload = payload

        def json(self):
            return self.payload

    for payload in ({"data": {"series": {"unexpected": "mapping"}}}, {"data": {"series": ["a", 1, None]}},
                    {"data": {"series": [{"endpointId": "x", "input": "nope"}, "str"]}}):
        monkeypatch.setattr(tracker.requests, "get", lambda *a, _p=payload, **k: Response(_p))
        store = {}
        sync_effective_prices_for_model("m/x", "m/x-1", store, W, 5.0, now=NOW,
                                        endpoints=endpoints_for(("openai", 0.2, 1.2)))  # must not raise
        assert not store["m/x"].get("observations")


def _run_env(monkeypatch, tmp_path, catalog_prompt="0.0000002"):
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": "m/x", "source": "manual", "order": 0}]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kw: None)
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: {
        "m/x": {"id": "m/x", "canonical_slug": "m/x-1", "pricing": {"prompt": catalog_prompt, "completion": "0.0000012"}}})
    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: {"series": [STD]})

    class _Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr("anticharon.tracker.datetime", _Clock)
    return cfg


STD_ENDPOINT = {"tag": "openai", "provider_slug": "openai", "provider_name": "OpenAI",
                "pricing": {"prompt": "2e-7", "completion": "1.2e-6", "input_cache_read": "2e-8"}}


def test_same_day_run_after_a_recalibration_rederives_instead_of_reusing_the_old_row(monkeypatch, tmp_path):
    from anticharon.tracker import run_tracker

    cfg = _run_env(monkeypatch, tmp_path)
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **k: [STD_ENDPOINT])
    history = tmp_path / "history.csv"
    first = run_tracker(config_path=cfg, history_path=history, no_hermes=True).prices_shortlist[0]
    assert first.price_1m == pytest.approx(blend(0.2, 0.02, 1.2))

    cfg.write_text(json.dumps({"shortlist": [{"model": "m/x", "source": "manual", "order": 0}],
                               "weight_uncached_prompt": 0.5, "weight_cached_prompt": 0.4968,
                               "weight_completion": 0.0032}), encoding="utf-8")
    second = run_tracker(config_path=cfg, history_path=history, no_hermes=True).prices_shortlist[0]  # same day, no --force

    expected = 0.2 * 0.5 + 0.02 * 0.4968 + 1.2 * 0.0032
    assert second.price_1m == pytest.approx(expected) and second.price_source == "live_quote"
    store = json.loads((tmp_path / "effective_prices.json").read_text(encoding="utf-8"))["m/x"]
    assert store["weights_used"] == [0.5, 0.4968, 0.0032]
    assert store["observations"][-1]["effective_price_1m"] == pytest.approx(expected)


def test_catalog_fallback_quote_is_flagged_and_not_stored_as_todays_history_point(monkeypatch, tmp_path):
    from anticharon.tracker import read_check_result, run_tracker

    cfg = _run_env(monkeypatch, tmp_path, catalog_prompt="0.0000064")  # headline blend differs from the history
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **k: [STD_ENDPOINT])
    history = tmp_path / "history.csv"
    run_tracker(config_path=cfg, history_path=history, no_hermes=True)  # a normal run first: history exists

    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *a, **k: [])  # endpoint route down
    result = run_tracker(config_path=cfg, history_path=history, no_hermes=True, force=True)

    row = result.prices_shortlist[0]
    assert "QUOTE_FROM_CATALOG" in [m.code for m in result.messages]
    stored = json.loads((tmp_path / "effective_prices.json").read_text(encoding="utf-8"))["m/x"]["observations"]
    assert stored[-1]["effective_price_1m"] != pytest.approx(row.price_1m)  # the headline is not history
    check = read_check_result(config_path=cfg, history_path=history, no_hermes=True).prices_shortlist[0]
    assert check.price_1m == pytest.approx(stored[-1]["effective_price_1m"])
    assert check.quote_1m == pytest.approx(row.price_1m)  # visible beside it as `last run quote`
