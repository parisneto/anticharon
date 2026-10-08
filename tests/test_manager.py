"""Tests for anticharon.manager: shortlist add/remove/list (unaffected by
the pricing-engine-v2 rework -- these operate on the model-id list only)."""

from anticharon.config import load_config
from anticharon.manager import add_model, list_models, remove_model


def test_model_manager_add_remove_list(tmp_path, monkeypatch):
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kwargs: {"google/gemini-3.7-flash": {}})
    temp_cfg = tmp_path / "shortlist.json"
    temp_cfg.write_text('{"shortlist": ["openai/gpt-5.6-luna"]}', encoding="utf-8")

    # 1. Add model with dry-run
    res_dry = add_model("google/gemini-3.7-flash", dry_run=True, config_path=temp_cfg)
    assert res_dry.status == "success"
    assert res_dry.dry_run is True
    assert len(res_dry.shortlist) == 2
    cfg_disk = load_config(temp_cfg)
    assert len(cfg_disk["shortlist"]) == 1

    # 2. Add model actual
    res_act = add_model("google/gemini-3.7-flash", dry_run=False, config_path=temp_cfg)
    assert res_act.status == "success"
    assert len(load_config(temp_cfg)["shortlist"]) == 2

    # 3. Add duplicate
    res_dup = add_model("google/gemini-3.7-flash", dry_run=False, config_path=temp_cfg)
    assert res_dup.status == "warning"
    assert len(load_config(temp_cfg)["shortlist"]) == 2

    # 4. Remove model
    res_rm = remove_model("google/gemini-3.7-flash", dry_run=False, config_path=temp_cfg)
    assert res_rm.status == "success"
    assert len(load_config(temp_cfg)["shortlist"]) == 1

    # 5. List models
    res_list = list_models(config_path=temp_cfg)
    assert len(res_list.shortlist) == 1


def test_exact_batch_slug_can_still_be_added_and_is_not_rewritten(tmp_path, monkeypatch):
    """EH-6: only normal discovery hides `:batch`; an exact add keeps the slug verbatim."""
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models",
                        lambda **kwargs: {"acme/model:batch": {}, "acme/model": {}})
    cfg = tmp_path / "shortlist.json"
    cfg.write_text('{"shortlist": ["openai/gpt-5.6-luna"]}', encoding="utf-8")

    res = add_model("acme/model:batch", dry_run=False, config_path=cfg)

    assert res.status == "success"
    assert load_config(cfg)["shortlist"] == ["openai/gpt-5.6-luna", "acme/model:batch"]
