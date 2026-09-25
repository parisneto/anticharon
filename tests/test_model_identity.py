"""Regressions for W2 shortlist identity, ownership, order and exact slugs."""

import json

from anticharon.config import default_model, load_config, update_config_shortlist
from anticharon.hermes import hermes_shortlist_divergent, sync_hermes_to_config
from anticharon.manager import add_model, remove_model
from anticharon.models import ModelPrice, PriceRecord
from anticharon.tracker import run_tracker


def test_flat_shortlist_migrates_to_source_objects_on_next_write(tmp_path):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": ["p/a", "p/b"]}), encoding="utf-8")
    assert load_config(path)["_shortlist_entries"] == [
        {"model": "p/a", "source": "manual"}, {"model": "p/b", "source": "manual"}
    ]
    update_config_shortlist(["p/a", "p/b", "p/c"], path)
    assert json.loads(path.read_text(encoding="utf-8"))["shortlist"] == [
        {"model": "p/a", "source": "manual"},
        {"model": "p/b", "source": "manual"},
        {"model": "p/c", "source": "manual"},
    ]


def test_hermes_sync_preserves_manual_entries_and_order_and_rejects_manual_removal(tmp_path, monkeypatch):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": [
        {"model": "h/old", "source": "hermes", "order": 0},
    ]}), encoding="utf-8")
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kwargs: {"m/custom": {}})
    assert add_model("m/custom", config_path=path).status == "success"
    changed, slugs, _ = sync_hermes_to_config({"all_models": ["h/new", "h/fallback"]}, path)
    assert changed
    assert slugs == ["h/new", "h/fallback", "m/custom"]
    entries = load_config(path)["_shortlist_entries"]
    assert entries[:2] == [
        {"model": "h/new", "source": "hermes", "order": 0},
        {"model": "h/fallback", "source": "hermes", "order": 1},
    ]
    assert remove_model("h/new", config_path=path).status == "refused"
    assert remove_model("m/custom", config_path=path).status == "success"


def test_divergence_compares_only_ordered_hermes_entries():
    assert not hermes_shortlist_divergent(["h/one", "h/two"], [
        {"model": "h/one", "source": "hermes", "order": 0},
        {"model": "m/extra", "source": "manual"},
        {"model": "h/two", "source": "hermes", "order": 1},
    ])
    assert hermes_shortlist_divergent(["h/one", "h/two"], [
        {"model": "h/two", "source": "hermes", "order": 0},
        {"model": "h/one", "source": "hermes", "order": 1},
    ])


def test_default_is_explicit_and_unmonitored_run_refuses_before_network(tmp_path, monkeypatch):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": ["p/first", "p/second"]}), encoding="utf-8")
    assert default_model(load_config(path)["_shortlist_entries"]) is None
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kwargs: (_ for _ in ()).throw(AssertionError("Hermes queried")))
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda **kwargs: (_ for _ in ()).throw(AssertionError("catalog queried")))
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pricing queried")))
    result = run_tracker(model_id="p/first-prefix", config_path=path, history_path=tmp_path / "history.csv")
    assert result.status == "refused"
    assert result.messages[0].code == "NOT_MONITORED"
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda **kwargs: {})
    local_result = run_tracker(dry_run=True, no_hermes=True, config_path=path, history_path=tmp_path / "history.csv")
    assert any(message.code == "NO_DEFAULT" for message in local_result.messages)


def test_add_model_requires_exact_catalog_slug_and_catalog_availability(tmp_path, monkeypatch):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": []}), encoding="utf-8")
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kwargs: {"p/model-lite": {}})
    result = add_model("p/model", config_path=path)
    assert result.status == "refused"
    assert result.messages[0].code == "NO_EXACT_MATCH"
    assert load_config(path)["shortlist"] == []
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kwargs: {})
    result = add_model("p/model", config_path=path)
    assert result.status == "error"
    assert result.messages[0].code == "CATALOG_UNAVAILABLE"


def test_tracker_does_not_substitute_prefix_alias(tmp_path, monkeypatch):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": ["p/model"]}), encoding="utf-8")
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda **kwargs: {
        "p/model-lite": {"id": "p/model-lite", "pricing": {"prompt": "0.000001", "completion": "0.000002"}}
    })
    result = run_tracker(dry_run=True, no_hermes=True, config_path=path, history_path=tmp_path / "history.csv")
    assert result.prices_shortlist == []
    assert [(message.code, message.model) for message in result.messages if message.model] == [
        ("NO_EXACT_MATCH", "p/model")
    ]


def test_tracker_reports_price_skip_reasons_per_model(tmp_path, monkeypatch):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": ["p/missing-price", "p/invalid-price"]}), encoding="utf-8")
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda **kwargs: {
        "p/missing-price": {"id": "p/missing-price", "pricing": {}},
        "p/invalid-price": {"id": "p/invalid-price", "pricing": {"prompt": "-1", "completion": "0.000002"}},
    })
    result = run_tracker(dry_run=True, no_hermes=True, config_path=path, history_path=tmp_path / "history.csv")
    assert {(message.code, message.model) for message in result.messages} >= {
        ("PRICE_UNAVAILABLE", "p/missing-price"), ("PRICE_INVALID", "p/invalid-price")
    }


def test_manual_default_is_explicit_and_replacing_it_clears_old_default(tmp_path, monkeypatch):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": [
        {"model": "p/first", "source": "manual", "order": 0},
        {"model": "p/second", "source": "manual"},
    ]}), encoding="utf-8")
    monkeypatch.setattr("anticharon.manager.get_hermes_models", lambda **kwargs: None)
    monkeypatch.setattr("anticharon.manager.fetch_openrouter_models", lambda **kwargs: {"p/second": {}})
    result = add_model("p/second", config_path=path, default=True)
    assert result.status == "success"
    entries = load_config(path)["_shortlist_entries"]
    assert default_model(entries) == "p/second"
    assert entries[0] == {"model": "p/first", "source": "manual"}


def test_not_monitored_history_is_refused_without_catalog_or_price_fetch(tmp_path, monkeypatch):
    from anticharon import mcp

    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": ["p/known"]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(path))
    monkeypatch.setattr(mcp, "run_tracker", lambda **kwargs: (_ for _ in ()).throw(AssertionError("tracker queried")))
    result = mcp.get_model_history("p/known-prefix")
    assert result.is_error is True
    envelope = json.loads(result.content[0].text)
    assert envelope["status"] == "refused"
    assert envelope["messages"][0]["code"] == "NOT_MONITORED"


def test_monitored_history_reads_local_storage_without_tracker_or_catalog(tmp_path, monkeypatch):
    from anticharon import mcp

    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": [{"model": "p/known", "source": "manual"}]}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(path))
    monkeypatch.setattr("anticharon.tracker.get_hermes_models", lambda **kwargs: None)
    monkeypatch.setattr("anticharon.tracker.read_history", lambda _: {"p/known": PriceRecord(
        model="p/known", last_updated="2026-09-25", effective_price_1m=1.0,
        advertised_prompt_1m=0.5, advertised_completion_1m=2.0, ma_3d=1.0, ma_7d=1.0,
        prices=[1.0] * 9,
    )})
    monkeypatch.setattr(mcp, "run_tracker", lambda **kwargs: (_ for _ in ()).throw(AssertionError("tracker queried")))
    result = mcp.get_model_history("p/known")
    envelope = result if isinstance(result, dict) else json.loads(result.content[0].text)
    assert envelope["prices_shortlist"][0]["model"] == "p/known"


def test_json_price_preserves_stored_identity_fields():
    payload = ModelPrice("p/model", 1.0, 1.0, 0.0, canonical_slug="p/model-2026", source="hermes", is_default=True).to_dict()
    assert payload["canonical_slug"] == "p/model-2026"
    assert payload["source"] == "hermes"
    assert payload["is_default"] is True
