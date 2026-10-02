"""AC-2 / D-3: Hermes sync persistence, idempotence, and default ownership.

Deterministic: a temp config file and in-memory detection payloads only.
"""

import json

from anticharon.config import default_model, load_config
from anticharon.hermes import (
    hermes_detection_messages,
    sync_hermes_to_config,
)
from anticharon.manager import list_models

SEQUENCE = ["a/default-1", "b/fallback-2", "c/fallback-3"]


def _detected(models=SEQUENCE, detection="complete"):
    return {"detection": detection, "default_model": models[0] if models else None,
            "all_models": list(models)}


def _write(tmp_path, shortlist):
    path = tmp_path / "shortlist.json"
    path.write_text(json.dumps({"shortlist": shortlist}), encoding="utf-8")
    return path


def _stored(path):
    return json.loads(path.read_text(encoding="utf-8"))["shortlist"]


def test_legacy_flat_list_with_same_sequence_is_persisted_with_metadata(tmp_path):
    path = _write(tmp_path, SEQUENCE)

    changed, _, _ = sync_hermes_to_config(_detected(), config_path=path)

    assert changed is True
    assert _stored(path) == [
        {"model": "a/default-1", "source": "hermes", "order": 0},
        {"model": "b/fallback-2", "source": "hermes", "order": 1},
        {"model": "c/fallback-3", "source": "hermes", "order": 2},
    ]


def test_persisted_metadata_survives_load_without_hermes_and_is_idempotent(tmp_path):
    path = _write(tmp_path, SEQUENCE)
    sync_hermes_to_config(_detected(), config_path=path)
    before = path.read_text(encoding="utf-8")

    # A later run that cannot detect Hermes loads legacy entries as manual:
    # persisted metadata must still yield the default and no divergence.
    entries = load_config(path, legacy_source="manual")["_shortlist_entries"]
    assert default_model(entries) == "a/default-1"
    assert hermes_detection_messages(_detected(), entries) == []

    changed_again, _, _ = sync_hermes_to_config(_detected(), config_path=path)
    assert changed_again is False
    assert path.read_text(encoding="utf-8") == before


def test_manual_models_are_retained_across_repeated_syncs(tmp_path):
    path = _write(tmp_path, [{"model": "m/manual", "source": "manual"}])

    sync_hermes_to_config(_detected(), config_path=path)
    sync_hermes_to_config(_detected(), config_path=path)

    models = [e["model"] for e in _stored(path)]
    assert models == [*SEQUENCE, "m/manual"]
    assert _stored(path)[-1] == {"model": "m/manual", "source": "manual"}


def test_manual_default_preference_is_stored_but_hermes_default_is_effective(tmp_path, monkeypatch):
    path = _write(tmp_path, [{"model": "m/manual", "source": "manual", "order": 0}])

    sync_hermes_to_config(_detected(), config_path=path)

    stored = _stored(path)
    assert {"model": "m/manual", "source": "manual", "order": 0} in stored  # preference preserved
    entries = load_config(path)["_shortlist_entries"]
    assert default_model(entries) == "a/default-1"

    monkeypatch.setattr("anticharon.manager.get_hermes_models", lambda **kw: None)
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    listed = list_models(config_path=path).entries
    assert [e["model"] for e in listed if e["is_default"]] == ["a/default-1"]


def test_incomplete_or_empty_detection_preserves_ownership_state(tmp_path):
    path = _write(tmp_path, [{"model": "m/manual", "source": "manual", "order": 0}])
    sync_hermes_to_config(_detected(), config_path=path)
    before = path.read_text(encoding="utf-8")

    partial = sync_hermes_to_config(_detected(["z/partial"], detection="incomplete"), config_path=path)
    unavailable_like = sync_hermes_to_config({"detection": "incomplete", "all_models": []}, config_path=path)
    no_detection_key = sync_hermes_to_config({}, config_path=path)

    assert (partial[0], unavailable_like[0], no_detection_key[0]) == (False, False, False)
    assert path.read_text(encoding="utf-8") == before
    assert default_model(load_config(path)["_shortlist_entries"]) == "a/default-1"


def test_authoritative_removal_restores_manual_default_preference(tmp_path):
    path = _write(tmp_path, [{"model": "m/manual", "source": "manual", "order": 0}])
    sync_hermes_to_config(_detected(), config_path=path)
    assert default_model(load_config(path)["_shortlist_entries"]) == "a/default-1"

    changed, _, _ = sync_hermes_to_config({"detection": "complete", "all_models": []}, config_path=path)

    assert changed is True
    assert _stored(path) == [{"model": "m/manual", "source": "manual", "order": 0}]
    assert default_model(load_config(path)["_shortlist_entries"]) == "m/manual"


def test_hermes_default_change_replaces_hermes_entries_only(tmp_path):
    path = _write(tmp_path, [{"model": "m/manual", "source": "manual", "order": 0}])
    sync_hermes_to_config(_detected(), config_path=path)

    sync_hermes_to_config(_detected(["n/new-default", "a/default-1"]), config_path=path)

    assert _stored(path) == [
        {"model": "n/new-default", "source": "hermes", "order": 0},
        {"model": "a/default-1", "source": "hermes", "order": 1},
        {"model": "m/manual", "source": "manual", "order": 0},
    ]
    assert default_model(load_config(path)["_shortlist_entries"]) == "n/new-default"
