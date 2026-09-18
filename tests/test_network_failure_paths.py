"""Deterministic, mocked failure-path tests for network calls in tracker.py.

See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-003 and #PE2-006:
every network-facing fetch function in tracker.py must degrade to its documented
empty value ([] or {}) uniformly across every distinct failure mode (timeout,
connection failure, HTTP error, malformed JSON, wrong response shape) -- never
raise, never return partial garbage -- so every downstream consumer can treat
that one signal consistently (AGENTS.md Rule 10: graceful fallback, never crash
the calling agent/cron script).
"""

import json

import requests

from anticharon.tracker import (
    fetch_effective_pricing_history,
    fetch_endpoint_policy_pricing,
    fetch_openrouter_models,
)


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, json_error=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


def test_fetch_endpoint_policy_pricing_timeout_returns_empty_list(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr("anticharon.tracker.requests.get", fake_get)
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_connection_error_returns_empty_list(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr("anticharon.tracker.requests.get", fake_get)
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_http_error_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(status_code=500),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_malformed_json_returns_empty_list(monkeypatch):
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_error=json.JSONDecodeError("bad json", "", 0)),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_wrong_response_shape_returns_empty_list(monkeypatch):
    """A response body that's valid JSON but not a dict with a "data" key
    (e.g. the route's shape changed to return a bare list) must not raise."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data=["unexpected", "shape"]),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_empty_successful_response_returns_empty_list(monkeypatch):
    """A genuinely successful 200 response with no endpoint data (e.g. a
    deprecated/delisted model) is indistinguishable from a fetch failure by
    design -- both mean "no real pricing data to judge routability from"."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": []}),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_success_returns_real_data(monkeypatch):
    real_data = [{"provider_name": "OpenAI", "pricing": {"prompt": "0.000002", "completion": "0.00001"}}]
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": real_data}),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == real_data


def test_fetch_endpoint_policy_pricing_nested_data_wrong_type_mapping_returns_empty_list(monkeypatch):
    """PE2-006 (independent retest round 4): valid JSON, valid top-level shape
    (a dict with a "data" key), but "data" itself is a mapping instead of a
    list -- e.g. the route started returning endpoints keyed by ID. Must
    degrade to [] rather than pass the mapping through: iterating a dict
    yields its string keys, and resolve_policy_pricing()'s per-endpoint
    ep.get(...) calls raise AttributeError on a str."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": {"ep1": {"provider_name": "OpenAI"}}}),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


def test_fetch_endpoint_policy_pricing_nested_data_wrong_element_type_returns_empty_list(monkeypatch):
    """PE2-006: "data" is itself a list (the expected outer type), but its
    elements are strings, not endpoint dicts -- the exact drift shape from the
    independent retest's report (`{"data": ["strings"]}`). Non-dict elements
    must be filtered out rather than passed through, since
    resolve_policy_pricing()'s ep.get(...) call would raise AttributeError on
    a str element."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": ["strings", "more strings"]}),
    )
    assert fetch_endpoint_policy_pricing("openai/gpt-5.6-luna-20260709") == []


# --- fetch_openrouter_models (bulk catalog): same failure normalization, returns {} ---


def test_fetch_openrouter_models_timeout_returns_empty_dict(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr("anticharon.tracker.requests.get", fake_get)
    assert fetch_openrouter_models() == {}


def test_fetch_openrouter_models_connection_error_returns_empty_dict(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr("anticharon.tracker.requests.get", fake_get)
    assert fetch_openrouter_models() == {}


def test_fetch_openrouter_models_http_error_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(status_code=503),
    )
    assert fetch_openrouter_models() == {}


def test_fetch_openrouter_models_malformed_json_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_error=json.JSONDecodeError("bad json", "", 0)),
    )
    assert fetch_openrouter_models() == {}


def test_fetch_openrouter_models_wrong_response_shape_returns_empty_dict(monkeypatch):
    """A response body that's valid JSON but a bare list, not {"data": [...]}."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data=["unexpected", "shape"]),
    )
    assert fetch_openrouter_models() == {}


def test_fetch_openrouter_models_success_returns_real_data(monkeypatch):
    real_data = [{"id": "openai/gpt-5.6-luna", "pricing": {"prompt": "0.0000002", "completion": "0.0000012"}}]
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": real_data}),
    )
    assert fetch_openrouter_models() == {"openai/gpt-5.6-luna": real_data[0]}


def test_fetch_openrouter_models_nested_data_wrong_type_mapping_returns_empty_dict(monkeypatch):
    """PE2-006: "data" is a mapping instead of a list of model dicts. Iterating
    a dict yields its string keys; `"id" in m`/`m["id"]` on a string key would
    silently misbehave or (for a non-string-like key) raise. Must degrade to {}."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": {"openai/gpt-5.6-luna": {"id": "openai/gpt-5.6-luna"}}}),
    )
    assert fetch_openrouter_models() == {}


def test_fetch_openrouter_models_nested_data_wrong_element_type_returns_empty_dict(monkeypatch):
    """PE2-006: "data" is a list (the expected outer type), but its elements
    are not dicts (e.g. bare integers) -- `"id" in m` raises TypeError for a
    non-iterable element like an int. Must skip non-dict elements rather than
    crash or silently misclassify them."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": [1, 2, 3]}),
    )
    assert fetch_openrouter_models() == {}


# --- fetch_effective_pricing_history (28-day backfill route): returns {} on failure ---


def test_fetch_effective_pricing_history_timeout_returns_empty_dict(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.Timeout("timed out")

    monkeypatch.setattr("anticharon.tracker.requests.get", fake_get)
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}


def test_fetch_effective_pricing_history_connection_error_returns_empty_dict(monkeypatch):
    def fake_get(*a, **kw):
        raise requests.exceptions.ConnectionError("connection refused")

    monkeypatch.setattr("anticharon.tracker.requests.get", fake_get)
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}


def test_fetch_effective_pricing_history_http_error_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(status_code=500),
    )
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}


def test_fetch_effective_pricing_history_malformed_json_returns_empty_dict(monkeypatch):
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_error=json.JSONDecodeError("bad json", "", 0)),
    )
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}


def test_fetch_effective_pricing_history_wrong_response_shape_returns_empty_dict(monkeypatch):
    """A response body that's valid JSON but a bare list, not {"data": {...}}."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data=["unexpected", "shape"]),
    )
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}


def test_fetch_effective_pricing_history_success_returns_real_data(monkeypatch):
    real_data = {"inputChartData": [{"x": "2026-09-15 00:00:00", "y": {"ep1": 0.05}}]}
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": real_data}),
    )
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == real_data


def test_fetch_effective_pricing_history_nested_data_wrong_type_empty_list_returns_empty_dict(monkeypatch):
    """PE2-006 (independent retest round 4): valid JSON, valid top-level shape
    (a dict with a "data" key), but "data" itself is a list instead of a
    mapping -- the exact reported reproduction (`{"data": []}`). Must degrade
    to {} rather than pass the list through: _reduce_to_daily_observations()
    immediately calls history_data.get(...), which raises AttributeError on
    a list."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": []}),
    )
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}


def test_fetch_effective_pricing_history_nested_data_wrong_type_nonempty_list_returns_empty_dict(monkeypatch):
    """PE2-006: same drift as above, but with a non-empty list -- confirms the
    guard checks the type, not just emptiness."""
    monkeypatch.setattr(
        "anticharon.tracker.requests.get",
        lambda *a, **kw: _FakeResponse(json_data={"data": ["unexpected", "entries"]}),
    )
    assert fetch_effective_pricing_history("openai/gpt-5.6-luna-20260709") == {}
