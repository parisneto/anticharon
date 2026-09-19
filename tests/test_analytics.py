"""Tests for anticharon.analytics: profile classification, sibling detection,
and the elapsed-days NEWLY_TRACKED threshold (PLAN.md "Analytics" section --
`tracking_days_elapsed < min_tracking_days_for_profile` drives NEWLY_TRACKED,
not a slot count, since backfill can leave gaps).
"""

from anticharon.analytics import (
    calculate_model_analytics,
    find_sibling_alternatives,
    parse_model_family,
)


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


# All classification tests below pass tracking_days_elapsed=30 (>= the 14-day
# default threshold) so they exercise the CV/trend-based classifications rather
# than being short-circuited by NEWLY_TRACKED.

def test_promo_ended_and_sunsetting_classification():
    candidates = {
        "google/gemini-3.7-flash": 0.75881,
        "google/gemini-3.8-flash": 0.75881,
    }
    hist_promo = [0.75881] * 4 + [0.37941] * 5
    an_promo = calculate_model_analytics(
        "google/gemini-3.7-flash", 0.75881, hist_promo, candidates, tracking_days_elapsed=30
    )
    assert an_promo.profile == "PROMO_ENDED"
    assert "PROMO_ENDED" in an_promo.badge
    assert an_promo.secondary_badge == "⚠️ SUNSETTING"
    assert round(an_promo.change_vs_30d_pct, 1) == 100.0


def test_stable_classification():
    hist_stable = [0.10088] * 6 + [0.10087] * 2 + [0.10088]
    an_stable = calculate_model_analytics(
        "google/gemini-2.5-flash-lite", 0.10088, hist_stable, tracking_days_elapsed=30
    )
    assert an_stable.profile == "STABLE"
    assert "STABLE" in an_stable.badge
    assert an_stable.volatility_cv_pct < 0.1


def test_volatile_classification():
    hist_vol = [0.85, 0.40, 0.95, 0.45, 0.90, 0.40, 0.85, 0.40, 0.90]
    an_vol = calculate_model_analytics(
        "nousresearch/hermes-3-70b", 0.65, hist_vol, tracking_days_elapsed=30
    )
    assert an_vol.profile == "VOLATILE"
    assert "VOLATILE" in an_vol.badge


def test_discounted_classification():
    hist_disc = [1.50, 1.50, 1.80, 2.00, 2.50, 3.00, 3.00, 3.00, 3.00]
    an_disc = calculate_model_analytics(
        "mistralai/mistral-large-2407", 1.50, hist_disc, tracking_days_elapsed=30
    )
    assert an_disc.profile == "DISCOUNTED"
    assert "DISCOUNTED" in an_disc.badge


def test_creeping_inflation_classification():
    hist_creep = [0.06534] * 4 + [0.06018] * 2 + [0.06017] * 2 + [0.06017]
    an_creep = calculate_model_analytics(
        "deepseek/deepseek-v4-flash-0731", 0.06534, hist_creep, tracking_days_elapsed=30
    )
    assert an_creep.profile == "CREEPING_INFLATION"
    assert "CREEPING" in an_creep.badge


# --- Elapsed-days NEWLY_TRACKED threshold (new in pricing-engine-v2) ---

def test_newly_tracked_when_elapsed_days_unknown():
    """tracking_days_elapsed=None (unknown) is the safe default -- NEWLY_TRACKED,
    even if the history slots happen to look mature."""
    hist_stable = [0.10088] * 9
    an = calculate_model_analytics("some/model", 0.10088, hist_stable)
    assert an.profile == "NEWLY_TRACKED"


def test_newly_tracked_below_min_tracking_days():
    hist_stable = [0.10088] * 9
    an = calculate_model_analytics(
        "some/model", 0.10088, hist_stable, tracking_days_elapsed=13, min_tracking_days_for_profile=14
    )
    assert an.profile == "NEWLY_TRACKED"


def test_classification_resumes_at_exact_threshold():
    hist_stable = [0.10088] * 9
    an = calculate_model_analytics(
        "some/model", 0.10088, hist_stable, tracking_days_elapsed=14, min_tracking_days_for_profile=14
    )
    assert an.profile != "NEWLY_TRACKED"


def test_min_tracking_days_for_profile_is_configurable():
    hist_stable = [0.10088] * 9
    an = calculate_model_analytics(
        "some/model", 0.10088, hist_stable, tracking_days_elapsed=5, min_tracking_days_for_profile=3
    )
    assert an.profile != "NEWLY_TRACKED"


def test_single_observation_golden_case():
    """EXECUTION_CONTRACT.md golden case: a single historical observation ->
    mean = observed value, profile = NEWLY_TRACKED, no synthetic observations
    fabricated to pad the remaining 8 slots (history_vector keeps real None)."""
    an = calculate_model_analytics(
        "brand/new-model", 0.05, [0.04, None, None, None, None, None, None, None, None],
        tracking_days_elapsed=1, min_tracking_days_for_profile=14,
    )
    assert an.profile == "NEWLY_TRACKED"
    assert an.history_vector["d1"] == 0.04
    assert an.history_vector["d2"] is None
    assert an.history_vector["d30"] is None


def test_single_observation_zero_dispersion_golden_case():
    """PE2-009: fills in EXECUTION_CONTRACT.md's Sample Golden Case's
    `<explicit Anticharon-defined behavior>` placeholder for dispersion. This
    is the literal "single historical observation" scenario the Contract
    describes -- a model tracked for exactly one day, zero backfill at all
    (every history slot null, only today's current price exists) -- distinct
    from `test_single_observation_golden_case` above, which uses two data
    points (current + one real historical slot).

    Expected per the Contract: mean = observed value, dispersion = 0.0%
    (the coefficient of variation of a single data point is mathematically
    zero -- there is no second point to vary against -- not undefined and
    not a fabricated nonzero guess), profile = NEWLY_TRACKED."""
    observed_value = 0.05
    an = calculate_model_analytics(
        "brand/new-model", observed_value, [None] * 9,
        tracking_days_elapsed=1, min_tracking_days_for_profile=14,
    )
    assert an.profile == "NEWLY_TRACKED"
    assert an.volatility_cv_pct == 0.0
    assert an.price_min_30d == observed_value  # "mean = observed value"
    assert an.price_max_30d == observed_value
    assert an.history_vector["now"] == observed_value
    assert all(an.history_vector[k] is None for k in an.history_vector if k != "now")


def test_nullable_slots_do_not_crash_mature_classification():
    """A model tracked long enough (elapsed >= threshold) but with backfill
    gaps (e.g. d1 and d15 populated, nothing between) must still classify
    without crashing or fabricating the missing points."""
    history_prices = [0.10, None, None, None, None, None, None, 0.10, None]  # d1, d15 only
    an = calculate_model_analytics(
        "gapped/model", 0.10, history_prices, tracking_days_elapsed=30, min_tracking_days_for_profile=14
    )
    assert an.profile != "NEWLY_TRACKED"
    assert an.history_vector["d2"] is None
    assert an.history_vector["d30"] is None
