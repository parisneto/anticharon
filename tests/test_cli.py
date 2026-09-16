"""Tests for anticharon.cli: help subcommand routing (unaffected by the
pricing-engine-v2 rework), and `model discover --zdr`'s filter-before-live-check
ordering + capped/warned ZDR live-check behavior."""

import argparse
import io
import json
from contextlib import redirect_stderr, redirect_stdout

from anticharon.cli import cmd_help, cmd_model


def _build_parsers():
    parser = argparse.ArgumentParser(prog="anticharon")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="Run help")
    model_p = subparsers.add_parser("model", help="Model help")
    model_subparsers = model_p.add_subparsers(dest="model_action")
    model_subparsers.add_parser("discover", help="Discover help")
    return parser, subparsers, model_subparsers


def test_help_top_level():
    parser, subparsers, model_subparsers = _build_parsers()
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=[]))
    assert code == 0
    assert "anticharon" in f.getvalue()


def test_help_subcommand():
    parser, subparsers, model_subparsers = _build_parsers()
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=["run"]))
    assert code == 0
    assert "run" in f.getvalue()


def test_help_nested_subcommand():
    parser, subparsers, model_subparsers = _build_parsers()
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=["model", "discover"]))
    assert code == 0
    assert "discover" in f.getvalue()


def test_help_unknown_target():
    parser, subparsers, model_subparsers = _build_parsers()
    f_err = io.StringIO()
    with redirect_stderr(f_err):
        code = cmd_help(parser, subparsers, model_subparsers, argparse.Namespace(target=["unknown"]))
    assert code == 2
    assert "unknown help target 'unknown'" in f_err.getvalue()


class _FakeCatalogResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}


def _discover_args(**overrides):
    base = dict(
        model_action="discover",
        query=None,
        promo=False,
        modality="text",
        filter=[],
        max_price=None,
        max_input_price=None,
        max_output_price=None,
        config=None,
        json=True,
        zdr=False,
    )
    base.update(overrides)
    return argparse.Namespace(**base)


def test_discover_zdr_only_live_checks_models_matching_local_filters(monkeypatch):
    """The live ZDR check must run against the query-narrowed candidate list, not
    the full catalog -- fetch_catalog() itself no longer live-checks ZDR at all."""
    fake_catalog = [
        {"id": "azure/model-a", "name": "Azure Model A", "canonical_slug": "azure/model-a",
         "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
        {"id": "other/model-b", "name": "Other Model B", "canonical_slug": "other/model-b",
         "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
        {"id": "other/model-c", "name": "Other Model C", "canonical_slug": "other/model-c",
         "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
    ]
    monkeypatch.setattr(
        "anticharon.discovery.requests.get",
        lambda url, timeout=10.0: _FakeCatalogResponse(fake_catalog),
    )

    checked_slugs = []

    def fake_endpoints(canonical_slug, timeout=10.0):
        checked_slugs.append(canonical_slug)
        return [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}]

    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", fake_endpoints)

    args = _discover_args(query="azure", zdr=True)
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_model(args)

    assert code == 0
    # Only "azure/model-a" matched the query filter -- the other 2 models must
    # never have been live-checked at all.
    assert checked_slugs == ["azure/model-a"]

    payload = json.loads(f.getvalue())
    ids = [m["id"] for m in payload["models"]]
    assert ids == ["azure/model-a"]
    assert "zdr_warning" not in payload


def test_discover_zdr_caps_live_checks_and_surfaces_warning(monkeypatch, tmp_path):
    """Exceeding max_zdr_check_count must not silently check only some models --
    a zdr_warning must be present in the JSON payload naming N of M."""
    fake_catalog = [
        {"id": f"provider/model-{i}", "name": f"Model {i}", "canonical_slug": f"provider/model-{i}",
         "pricing": {"prompt": f"0.00000{i + 1}", "completion": f"0.00000{i + 1}"}}
        for i in range(5)
    ]
    monkeypatch.setattr(
        "anticharon.discovery.requests.get",
        lambda url, timeout=10.0: _FakeCatalogResponse(fake_catalog),
    )

    checked_slugs = []

    def fake_endpoints(canonical_slug, timeout=10.0):
        checked_slugs.append(canonical_slug)
        return [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}]

    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", fake_endpoints)

    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({"shortlist": [], "max_zdr_check_count": 2}), encoding="utf-8")

    args = _discover_args(config=str(cfg_path), zdr=True)
    f = io.StringIO()
    with redirect_stdout(f):
        code = cmd_model(args)

    assert code == 0
    assert len(checked_slugs) == 2  # capped, not all 5

    payload = json.loads(f.getvalue())
    assert "zdr_warning" in payload
    assert "2 of 5" in payload["zdr_warning"]
