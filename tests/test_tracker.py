"""Tests for anticharon.tracker's price-picker guard against sentinel pricing.

Only covers the negative-sentinel-price regression (see tests/test_pricing.py for
context). The broader cold-start / same-day-rerun / effective-price rework this
file name is reserved for in docs/plans/pricing-engine-v2/PLAN.md is a later phase.
"""

import json

from anticharon.tracker import run_tracker


def test_run_tracker_skips_sentinel_priced_model(monkeypatch, tmp_path):
    """openrouter/auto-beta (a meta-router) lists pricing prompt/completion as "-1" --
    a real, live-verified case, not hypothetical. run_tracker must skip it rather
    than surface a negative $/1M as though it were the cheapest real price."""

    def fake_fetch_openrouter_models(timeout: float = 10.0):
        return {
            "openrouter/auto-beta": {
                "id": "openrouter/auto-beta",
                "pricing": {"prompt": "-1", "completion": "-1"},
            },
            "openai/gpt-5.6-luna": {
                "id": "openai/gpt-5.6-luna",
                "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
            },
        }

    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", fake_fetch_openrouter_models)

    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({
        "shortlist": ["openrouter/auto-beta", "openai/gpt-5.6-luna"],
        "weight_prompt": 0.9971,
        "weight_completion": 0.0029,
    }), encoding="utf-8")
    hist_path = tmp_path / "history.csv"

    result = run_tracker(
        dry_run=True,
        config_path=cfg_path,
        history_path=hist_path,
        no_hermes=True,
    )

    model_ids = [p.model for p in result.prices_shortlist]
    assert "openrouter/auto-beta" not in model_ids
    assert "openai/gpt-5.6-luna" in model_ids
    assert all(p.price_1m >= 0 for p in result.prices_shortlist)
