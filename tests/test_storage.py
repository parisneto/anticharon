"""Tests for anticharon.storage: history.csv (new 16-column schema, nullable
slots) and the granular effective_prices.json store + derivation logic that
replaces the old per-run slot-shift (see PLAN.md "Storage architecture" /
"Same-day-rerun bug fix" -- deriving fresh from dated observations each time
makes a same-day rerun a no-op for d1..d30 by construction).
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from anticharon.storage import (
    derive_history_window,
    is_model_backfill_stale,
    read_effective_prices,
    read_history,
    write_effective_prices,
    write_history,
)


def test_history_csv_roundtrip_new_schema(tmp_path):
    temp_csv = tmp_path / "history.csv"
    records = [
        [
            "openai/gpt-5.6-luna", "2026-09-16T20:00:00Z", 0.10389, 0.20000, 1.20000,
            0.10389, 0.10389,
            0.10389, 0.10200, None, None, None, None, None, None, None,
        ],
        [
            "deepseek/deepseek-v4-flash-0731", "2026-09-16T20:00:00Z", 0.09030, 0.07000, 0.28000,
            0.09030, 0.09030,
            0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030, 0.09030,
        ],
    ]
    write_history(records, temp_csv)
    history = read_history(temp_csv)

    assert "openai/gpt-5.6-luna" in history
    assert "deepseek/deepseek-v4-flash-0731" in history

    luna = history["openai/gpt-5.6-luna"]
    assert abs(luna.effective_price_1m - 0.10389) < 1e-5
    assert abs(luna.advertised_prompt_1m - 0.20000) < 1e-5
    assert abs(luna.advertised_completion_1m - 1.20000) < 1e-5
    assert len(luna.prices) == 9
    # Nullable slots round-trip as None, not a fabricated 0.0/duplicate.
    assert luna.prices[2] is None
    assert luna.prices[0] == pytest.approx(0.10389, abs=1e-5)

    flash = history["deepseek/deepseek-v4-flash-0731"]
    assert all(p is not None for p in flash.prices)


def test_history_csv_missing_file_returns_empty(tmp_path):
    assert read_history(tmp_path / "does_not_exist.csv") == {}


def test_history_csv_old_pre_rename_format_degrades_gracefully(tmp_path):
    """PE2-009: PLAN.md decided (2026-09-15, "Core pricing semantics"; confirmed
    by commit 648798e) NOT to add a backward-compatibility shim for the
    `current_price_1m` -> `effective_price_1m` rename -- a stale local
    `history.csv` from before the rename should simply be deleted/regenerated.
    EXECUTION_CONTRACT.md's Storage acceptance criteria requires this decision
    be "either backward-compatible OR has an explicit, TESTED migration/
    fallback path" -- this test is that missing test. The old 14-column
    schema (`current_price_1m` header, no `advertised_*` columns) must
    degrade gracefully to empty history, never crash and never misparse a
    stale row's columns into the new schema's different column positions."""
    old_format_csv = (
        "model,last_updated,current_price_1m,ma_3d,ma_7d,d1,d2,d3,d4,d5,d6,d7,d15,d30\n"
        "openai/gpt-5.6-luna,2026-08-24T20:00:00Z,0.10389,0.10389,0.10389,"
        "0.10389,0.10389,0.10389,0.10389,0.10389,0.10389,0.10389,0.10389,0.10389\n"
    )
    old_csv_path = tmp_path / "history.csv"
    old_csv_path.write_text(old_format_csv, encoding="utf-8")

    history = read_history(old_csv_path)
    assert history == {}  # graceful fallback, never a fabricated/misparsed partial read


def test_effective_prices_store_roundtrip(tmp_path):
    path = tmp_path / "effective_prices.json"
    store = {
        "openai/gpt-5.6-luna": {
            "canonical_slug": "openai/gpt-5.6-luna-20260709",
            "first_seen": "2026-08-16",
            "last_synced": "2026-09-16T12:00:00+00:00",
            "observations": [{"date": "2026-09-15", "effective_price_1m": 0.05}],
        }
    }
    write_effective_prices(store, path)
    loaded = read_effective_prices(path)
    assert loaded == store


def test_effective_prices_store_missing_file_returns_empty(tmp_path):
    assert read_effective_prices(tmp_path / "nope.json") == {}


def test_effective_prices_store_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "effective_prices.json"
    path.write_text("{not valid json", encoding="utf-8")
    assert read_effective_prices(path) == {}


def test_is_model_backfill_stale_no_entry():
    assert is_model_backfill_stale({}, "openai/gpt-5.6-luna") is True


def test_is_model_backfill_stale_fresh_entry():
    now = datetime.now(timezone.utc)
    store = {"openai/gpt-5.6-luna": {"last_synced": now.isoformat()}}
    assert is_model_backfill_stale(store, "openai/gpt-5.6-luna", now=now) is False


def test_is_model_backfill_stale_old_entry():
    now = datetime.now(timezone.utc)
    stale_time = now - timedelta(hours=48)
    store = {"openai/gpt-5.6-luna": {"last_synced": stale_time.isoformat()}}
    assert is_model_backfill_stale(store, "openai/gpt-5.6-luna", max_age_hours=24.0, now=now) is True


def test_derive_history_window_exact_offsets():
    today = date(2026, 9, 16)
    observations = [
        {"date": "2026-09-15", "effective_price_1m": 0.10},  # d1
        {"date": "2026-09-14", "effective_price_1m": 0.11},  # d2
        {"date": "2026-09-13", "effective_price_1m": 0.12},  # d3
        {"date": "2026-09-01", "effective_price_1m": 0.20},  # d15
        {"date": "2026-08-17", "effective_price_1m": 0.30},  # d30
    ]
    result = derive_history_window(observations, today=today)
    slots = result["slots"]
    assert slots["d1"] == pytest.approx(0.10)
    assert slots["d2"] == pytest.approx(0.11)
    assert slots["d3"] == pytest.approx(0.12)
    assert slots["d4"] is None
    assert slots["d15"] == pytest.approx(0.20)
    assert slots["d30"] == pytest.approx(0.30)
    assert result["ma_3d"] == pytest.approx((0.10 + 0.11 + 0.12) / 3)
    assert result["ma_7d"] == pytest.approx((0.10 + 0.11 + 0.12) / 3)  # only d1-d3 present among d1-d7


def test_derive_history_window_single_observation_golden_case():
    """EXECUTION_CONTRACT.md golden case: single historical observation ->
    mean = observed value, profile = NEWLY_TRACKED, no synthetic observations."""
    today = date(2026, 9, 16)
    observations = [{"date": "2026-09-15", "effective_price_1m": 0.10}]
    result = derive_history_window(observations, today=today)
    assert result["slots"]["d1"] == pytest.approx(0.10)
    assert all(v is None for k, v in result["slots"].items() if k != "d1")
    assert result["ma_3d"] == pytest.approx(0.10)
    assert result["ma_7d"] == pytest.approx(0.10)


def test_derive_history_window_no_observations_is_all_null():
    today = date(2026, 9, 16)
    result = derive_history_window([], today=today)
    assert all(v is None for v in result["slots"].values())
    assert result["ma_3d"] is None
    assert result["ma_7d"] is None


def test_derive_history_window_same_day_rerun_is_idempotent():
    """Same-day-rerun bug fix: deriving fresh from dated observations twice in
    the same day produces identical d1..d30, since there's no "shift" to
    double-apply -- unlike the old `[current] + prev[:8]` approach."""
    today = date(2026, 9, 16)
    observations = [{"date": "2026-09-15", "effective_price_1m": 0.10}]
    first_run = derive_history_window(observations, today=today)
    second_run = derive_history_window(observations, today=today)
    assert first_run["slots"] == second_run["slots"]
    assert first_run["ma_3d"] == second_run["ma_3d"]


def test_derive_history_window_multiple_same_day_observations_picks_min():
    today = date(2026, 9, 16)
    observations = [
        {"date": "2026-09-15", "effective_price_1m": 0.30},
        {"date": "2026-09-15", "effective_price_1m": 0.10},
    ]
    result = derive_history_window(observations, today=today)
    assert result["slots"]["d1"] == pytest.approx(0.10)
