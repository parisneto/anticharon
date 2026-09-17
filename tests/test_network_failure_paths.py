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
