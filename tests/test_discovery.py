"""Tests for anticharon.discovery's catalog fetch guard against sentinel pricing.

Only covers the negative-sentinel-price regression (see tests/test_pricing.py for
context). fetch_catalog() browses the *full* public catalog, so this is more
exposed than tracker.py's shortlist path -- a real user running
`anticharon model discover` would otherwise see openrouter/auto-beta ranked as
the globally cheapest model.
"""

from anticharon.discovery import fetch_catalog


class _FakeResponse:
    status_code = 200

    def __init__(self, data):
        self._data = data

    def json(self):
        return {"data": self._data}


def test_fetch_catalog_skips_sentinel_priced_model(monkeypatch):
    fake_data = [
        {
            "id": "openrouter/auto-beta",
            "name": "Auto Router (Beta)",
            "pricing": {"prompt": "-1", "completion": "-1"},
        },
        {
            "id": "openai/gpt-5.6-luna",
            "name": "OpenAI: GPT-5.6 Luna",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
        },
    ]

    def fake_get(url, timeout=10.0):
        return _FakeResponse(fake_data)

    monkeypatch.setattr("anticharon.discovery.requests.get", fake_get)

    catalog = fetch_catalog()
    ids = [m.id for m in catalog]

    assert "openrouter/auto-beta" not in ids
    assert "openai/gpt-5.6-luna" in ids
    assert all(m.blended_price_1m >= 0 for m in catalog)
