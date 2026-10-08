"""Tests for anticharon.analytics: profile classification, sibling detection,
and the observed-days NEWLY_TRACKED threshold. Analytics read dated observations
(the `effective_prices.json` shape); maturity is the count of distinct valid
observed calendar days, with no dependence on `first_seen`.
"""

from datetime import date, timedelta

from anticharon.analytics import (
    calculate_model_analytics,
    find_sibling_alternatives,
    parse_model_family,
    valid_observations,
)

TODAY = date(2026, 10, 1)


def obs(price_by_days_ago):
    """Observation dicts from {days_ago: price} (or a callable over 1..30)."""
    return [
        {"date": (TODAY - timedelta(days=n)).isoformat(), "effective_price_1m": p}
        for n, p in sorted(price_by_days_ago.items())
    ]


def run(model, current, price_by_days_ago, **kwargs):
    return calculate_model_analytics(model, current, obs(price_by_days_ago), TODAY, **kwargs)


def test_parse_model_family():
    prov, prefix, ver, suffix = parse_model_family("google/gemini-3.7-flash")
    assert prov == "google"
    assert prefix == "gemini-"
    assert ver == 3.7
    assert suffix == "-flash"


def test_find_sibling_alternatives_newer_version():
    candidates = {
        "google/gemini-3.7-flash": 0.75881,
        "google/gemini-3.8-flash": 0.75881,
        "google/gemini-2.5-flash-lite": 0.10088
    }
    sibs = find_sibling_alternatives("google/gemini-3.7-flash", 0.75881, candidates)
    assert len(sibs) == 1
    assert sibs[0].model == "google/gemini-3.8-flash"
    assert sibs[0].relation == "newer_version"



# Classification series have 30 real observations, past the 14-day default
# threshold, so they exercise the CV/trend classifications.

def test_promo_ended_and_sunsetting_classification():
    candidates = {"google/gemini-3.7-flash": 0.75881, "google/gemini-3.8-flash": 0.75881}
    series = {n: (0.75881 if n <= 7 else 0.37941) for n in range(1, 31)}
    an = run("google/gemini-3.7-flash", 0.75881, series, candidate_prices=candidates)
    assert an.profile == "PROMO_ENDED"
    assert "PROMO_ENDED" in an.badge
    assert an.secondary_badge == "⚠️ SUNSETTING"
    assert round(an.change_vs_30d_pct, 1) == 100.0


def test_stable_classification():
    series = {n: (0.10087 if n in (8, 9) else 0.10088) for n in range(1, 31)}
    an = run("google/gemini-2.5-flash-lite", 0.10088, series)
    assert an.profile == "STABLE"
    assert "STABLE" in an.badge
    assert an.volatility_cv_pct < 0.1


def test_volatile_classification():
    series = {n: (0.85 if n % 2 else 0.40) for n in range(1, 29)}
    an = run("nousresearch/hermes-3-70b", 0.65, series)
    assert an.profile == "VOLATILE"
    assert "VOLATILE" in an.badge


def test_discounted_classification():
    series = {n: (1.50 if n <= 3 else 3.00) for n in range(1, 31)}
    an = run("mistralai/mistral-large-2407", 1.50, series)
    assert an.profile == "DISCOUNTED"
    assert "DISCOUNTED" in an.badge


def test_creeping_inflation_classification():
    series = {n: (0.06534 if n <= 4 else 0.06018 if n <= 14 else 0.06017) for n in range(1, 31)}
    an = run("deepseek/deepseek-v4-flash-0731", 0.06534, series)
    assert an.profile == "CREEPING_INFLATION"
    assert "CREEPING" in an.badge


# --- AC-1: maturity from distinct observed days in the observation window ---

def test_day_zero_backfill_gets_normal_profile_with_evidence():
    """An established model: 28 real backfilled days on its first Anticharon run."""
    an = run("some/model", 0.10088, {n: 0.10088 for n in range(1, 29)})
    assert an.profile == "STABLE"
    assert an.observation_count == 28
    assert an.earliest_observation == (TODAY - timedelta(days=28)).isoformat()
    assert an.latest_observation == (TODAY - timedelta(days=1)).isoformat()
    assert an.coverage_days == 28
    assert an.classification_reason == "28 distinct observed days ≥ 14 required for classification."


def test_new_release_with_five_days_stays_newly_tracked():
    an = run("some/model", 0.10, {n: 0.10 for n in range(1, 6)})
    assert an.profile == "NEWLY_TRACKED"
    assert an.observation_count == 5
    assert an.classification_reason == "5 distinct observed days < 14 required for classification."
    assert "5 observed days" in an.recommendation


def test_threshold_is_exact_observed_day_count():
    below = run("some/model", 0.10, {n: 0.10 for n in range(1, 14)})
    at = run("some/model", 0.10, {n: 0.10 for n in range(1, 15)})
    assert below.profile == "NEWLY_TRACKED"
    assert at.profile != "NEWLY_TRACKED"


def test_min_tracking_days_for_profile_is_configurable():
    series = {n: 0.10 for n in range(1, 6)}
    assert run("some/model", 0.10, series, min_tracking_days_for_profile=5).profile != "NEWLY_TRACKED"
    assert run("some/model", 0.10, series, min_tracking_days_for_profile=6).profile == "NEWLY_TRACKED"


def test_no_observations_is_newly_tracked_with_empty_evidence():
    an = run("brand/new-model", 0.05, {})
    assert an.profile == "NEWLY_TRACKED"
    assert an.observation_count == 0
    assert an.earliest_observation is None and an.latest_observation is None
    assert an.coverage_days == 0
    assert an.volatility_cv_pct == 0.0
    assert an.price_min_30d == an.price_max_30d == 0.05
    assert all(an.history_vector[k] is None for k in an.history_vector if k != "now")


def test_gaps_are_preserved_and_count_only_observed_days():
    every_other_day = {n: 0.10 for n in range(2, 30, 2)}  # 14 observed days, days 2..28
    an = run("gapped/model", 0.10, every_other_day)
    assert an.observation_count == 14
    assert an.coverage_days == 27
    assert an.profile != "NEWLY_TRACKED"
    assert an.history_vector["d1"] is None
    assert an.history_vector["d2"] == 0.10
    thirteen = run("gapped/model", 0.10, {n: 0.10 for n in range(2, 28, 2)})
    assert thirteen.observation_count == 13
    assert thirteen.profile == "NEWLY_TRACKED"


def test_duplicate_dates_count_once_and_minimum_wins():
    entries = obs({n: 0.20 for n in range(1, 14)}) + obs({n: 0.10 for n in range(1, 14)})
    an = calculate_model_analytics("dup/model", 0.10, entries, TODAY)
    assert an.observation_count == 13
    assert an.profile == "NEWLY_TRACKED"
    assert an.price_max_30d == 0.10  # the 0.20 duplicates never survive
    assert valid_observations(entries, TODAY)[TODAY - timedelta(days=1)] == 0.10


def test_zero_prices_are_valid_observations():
    series = {n: 0.0 for n in range(1, 15)}
    an = run("free/model", 0.0, series)
    assert an.observation_count == 14
    assert an.profile == "STABLE"
    assert an.volatility_cv_pct == 0.0
    assert an.history_vector["d1"] == 0.0


def test_zero_baseline_then_paid_price_has_no_percentage_but_shows_the_rise():
    series = {0: 0.10, **{n: 0.0 for n in range(1, 31)}}
    an = run("free/model", None, series)
    assert an.profile != "NEWLY_TRACKED"
    assert an.change_vs_30d_pct is None
    assert "↑" in an.trajectory_sparkline
    assert an.profile not in {"DISCOUNTED", "CREEPING_INFLATION"}


def test_zero_baseline_and_zero_price_is_flat():
    an = run("free/model", 0.0, {n: 0.0 for n in range(1, 31)})
    assert an.change_vs_30d_pct == 0.0


def test_invalid_observations_are_not_counted():
    good = obs({n: 0.10 for n in range(1, 14)})
    bad = [
        {"date": "not-a-date", "effective_price_1m": 0.1},
        {"date": (TODAY - timedelta(days=14)).isoformat(), "effective_price_1m": -0.1},
        {"date": (TODAY - timedelta(days=15)).isoformat(), "effective_price_1m": float("nan")},
        {"date": (TODAY - timedelta(days=16)).isoformat(), "effective_price_1m": float("inf")},
        {"date": (TODAY - timedelta(days=17)).isoformat(), "effective_price_1m": "abc"},
        {"date": (TODAY + timedelta(days=1)).isoformat(), "effective_price_1m": 0.1},
        {"date": (TODAY - timedelta(days=31)).isoformat(), "effective_price_1m": 0.1},
        {"date": (TODAY - timedelta(days=18)).isoformat()},
    ]
    an = calculate_model_analytics("some/model", 0.10, good + bad, TODAY)
    assert an.observation_count == 13
    assert an.profile == "NEWLY_TRACKED"


def test_observation_window_includes_today_and_thirty_days_back():
    edge = {"date": (TODAY - timedelta(days=30)).isoformat(), "effective_price_1m": 0.1}
    today_obs = {"date": TODAY.isoformat(), "effective_price_1m": 0.1}
    assert set(valid_observations([edge, today_obs], TODAY)) == {TODAY - timedelta(days=30), TODAY}


# --- Review remediation: authoritative observations, unavailable baselines ---

def test_stored_today_observation_overrides_a_separate_current_quote():
    series = {n: 1.0 for n in range(14)}  # includes today (days_ago 0)
    an = run("some/model", 2.0, series)
    assert an.profile != "VOLATILE"
    assert an.volatility_cv_pct == 0.0
    assert an.current_price_source == "observation"
    assert an.current_price_used == 1.0


def test_latest_observation_beats_a_separate_quote_even_when_today_is_missing():
    """Same stored evidence -> same classification on every surface: a quote
    never changes the result while any observation exists."""
    series = {n: 1.0 for n in range(1, 15)}
    with_quote = run("some/model", 2.0, series)
    without_quote = run("some/model", None, series)
    assert with_quote.to_dict() == without_quote.to_dict()
    assert with_quote.current_price_source == "observation"
    assert with_quote.current_price_used == 1.0
    assert with_quote.price_max_30d == 1.0


def test_quote_is_used_and_labelled_only_with_no_observations():
    an = run("some/model", 2.0, {})
    assert an.current_price_source == "quote"
    assert an.current_price_used == 2.0
    assert an.profile == "NEWLY_TRACKED"


def test_missing_30d_baseline_is_unavailable_not_fabricated():
    an = run("some/model", 1.1, {n: 1.0 for n in range(1, 15)})  # days 1..14 only
    assert an.profile != "CREEPING_INFLATION"
    assert an.change_vs_30d_pct is None
    assert an.to_dict()["change_vs_30d_pct"] is None
    assert "n/a" in an.trajectory_sparkline
    assert "30d" not in an.recommendation


def test_baseline_dependent_profiles_require_their_baselines():
    # DISCOUNTED and SUNSETTING need a real 30-day baseline.
    discount = run("some/model", 1.5, {n: (1.5 if n <= 3 else 3.0) for n in range(1, 15)})
    assert discount.profile != "DISCOUNTED"
    sibling = run("google/gemini-3.7-flash", 0.76, {n: 0.76 for n in range(1, 15)},
                  candidate_prices={"google/gemini-3.7-flash": 0.76, "google/gemini-3.8-flash": 0.76})
    assert sibling.profile != "SUNSETTING"
    # With a day-30 observation the same series classifies normally.
    with_baseline = run("google/gemini-3.7-flash", 0.76, {n: 0.76 for n in [*range(1, 15), 30]},
                        candidate_prices={"google/gemini-3.7-flash": 0.76, "google/gemini-3.8-flash": 0.76})
    assert with_baseline.profile == "SUNSETTING"
    assert with_baseline.change_vs_30d_pct == 0.0


def test_promo_ended_without_30d_baseline_uses_the_available_baseline():
    series = {n: (1.0 if n <= 3 else 0.5) for n in range(1, 15)}
    an = run("some/model", 1.0, series)
    assert an.profile == "PROMO_ENDED"
    assert an.change_vs_30d_pct is None
    assert "+100.0%" in an.recommendation


def test_single_observation_on_the_day_30_cutoff_is_a_valid_baseline():
    an = run("some/model", None, {30: 2.0}, min_tracking_days_for_profile=1)
    assert an.history_vector["d30"] == 2.0
    assert an.change_vs_30d_pct == 0.0
    assert "n/a" not in an.trajectory_sparkline
