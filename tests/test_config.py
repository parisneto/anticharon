"""Tests for anticharon.config: cache-aware 3-way default weights and calibration."""

from pathlib import Path

import pytest

from anticharon.config import DEFAULT_CONFIG, load_config, update_config_weights
from anticharon.log_parser import parse_activity_log

SAMPLE_DIR = Path(__file__).parent.parent / "docs" / "sample"


def test_default_config_has_3way_weights():
    assert "weight_uncached_prompt" in DEFAULT_CONFIG
    assert "weight_cached_prompt" in DEFAULT_CONFIG
    assert "weight_completion" in DEFAULT_CONFIG
    assert "weight_prompt" not in DEFAULT_CONFIG  # legacy 2-way key is gone, not just unused
    total = (
        DEFAULT_CONFIG["weight_uncached_prompt"]
        + DEFAULT_CONFIG["weight_cached_prompt"]
        + DEFAULT_CONFIG["weight_completion"]
    )
    assert total == pytest.approx(1.0, abs=1e-4)


def test_default_config_has_min_tracking_days_for_profile():
    assert DEFAULT_CONFIG["min_tracking_days_for_profile"] == 14


def test_update_config_weights_writes_3way(tmp_path):
    cfg_path = tmp_path / "shortlist.json"
    update_config_weights(0.25, 0.72, 0.03, cfg_path)
    cfg = load_config(cfg_path)
    assert cfg["weight_uncached_prompt"] == pytest.approx(0.25)
    assert cfg["weight_cached_prompt"] == pytest.approx(0.72)
    assert cfg["weight_completion"] == pytest.approx(0.03)


def test_config_calibration_from_real_sample(tmp_path):
    """Regression: calibrate against a real sample log and persist the
    cache-aware 3-way split (superseding the old 2-way weight_prompt)."""
    sample_csv = SAMPLE_DIR / "openrouter_activity_2026-08-24.csv"
    mix = parse_activity_log(sample_csv)
    cfg_path = tmp_path / "shortlist.json"
    update_config_weights(mix.weight_uncached_prompt, mix.weight_cached_prompt, mix.weight_completion, cfg_path)

    cfg = load_config(cfg_path)
    assert cfg["weight_uncached_prompt"] == pytest.approx(mix.weight_uncached_prompt, abs=1e-4)
    assert cfg["weight_cached_prompt"] == pytest.approx(mix.weight_cached_prompt, abs=1e-4)
    assert cfg["weight_completion"] == pytest.approx(0.002937, abs=1e-4)
