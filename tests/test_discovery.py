"""Tests for anticharon.discovery's catalog fetch guard against sentinel pricing.

Only covers the negative-sentinel-price regression (see tests/test_pricing.py for
context). fetch_catalog() browses the *full* public catalog, so this is more
exposed than tracker.py's shortlist path -- a real user running
`anticharon model discover` would otherwise see openrouter/auto-beta ranked as
the globally cheapest model.
"""

import pytest

from anticharon.discovery import CatalogModel, fetch_catalog, filter_catalog


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


def test_fetch_catalog_uses_cache_aware_3way_blend(monkeypatch):
    """blended_price_1m must use the model's own pricing.input_cache_read (confirmed
    present per-model in the bulk catalog) with the 3-way weights, not the removed
    2-way legacy formula."""
    fake_data = [
        {
            "id": "openai/gpt-5.6-luna",
            "name": "OpenAI: GPT-5.6 Luna",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012", "input_cache_read": "0.00000002"},
        },
    ]
    monkeypatch.setattr("anticharon.discovery.requests.get", lambda url, timeout=10.0: _FakeResponse(fake_data))

    catalog = fetch_catalog(weight_uncached_prompt=0.2, weight_cached_prompt=0.79, weight_completion=0.01)
    assert len(catalog) == 1
    m = catalog[0]
    expected = 0.2 * m.prompt_price_1m + 0.79 * 0.02 + 0.01 * m.completion_price_1m
    assert m.blended_price_1m == pytest.approx(expected, abs=1e-6)


def test_fetch_catalog_zdr_only_excludes_unroutable_models(monkeypatch):
    fake_data = [
        {"id": "openai/gpt-5.6-sol", "name": "Sol", "canonical_slug": "openai/gpt-5.6-sol-20260709",
         "pricing": {"prompt": "0.000002", "completion": "0.00001"}},
        {"id": "azure-friendly/model", "name": "Azure Friendly", "canonical_slug": "azure-friendly/model",
         "pricing": {"prompt": "0.000002", "completion": "0.00001"}},
    ]
    monkeypatch.setattr("anticharon.discovery.requests.get", lambda url, timeout=10.0: _FakeResponse(fake_data))

    def fake_endpoints(canonical_slug, timeout=10.0):
        if canonical_slug == "azure-friendly/model":
            return [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}]
        return [{"provider_info": {"dataPolicy": {"retainsPrompts": True}}}]

    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", fake_endpoints)

    catalog = fetch_catalog(zdr_only=True)
    ids = [m.id for m in catalog]
    assert "openai/gpt-5.6-sol" not in ids
    assert "azure-friendly/model" in ids


def test_filter_catalog_multi_criteria():
    dummy_catalog = [
        CatalogModel(
            id="google/gemini-2.5-flash-lite",
            name="Google: Gemini 2.5 Flash Lite",
            context_length=1048576,
            prompt_price_1m=0.10,
            completion_price_1m=0.40,
            blended_price_1m=0.10087,
            is_promo=False,
            output_modalities=["text"]
        ),
        CatalogModel(
            id="nvidia/nemotron-3.5-lightning:free",
            name="NVIDIA: Nemotron (free)",
            context_length=1000000,
            prompt_price_1m=0.0,
            completion_price_1m=0.0,
            blended_price_1m=0.0,
            is_promo=True,
            output_modalities=["text"]
        ),
        CatalogModel(
            id="openai/gpt-5.6-luna",
            name="OpenAI: GPT-5.6 Luna",
            context_length=1048576,
            prompt_price_1m=0.20,
            completion_price_1m=1.20,
            blended_price_1m=0.20290,
            is_promo=False,
            output_modalities=["text"]
        ),
        CatalogModel(
            id="anthropic/claude-3-opus",
            name="Anthropic: Claude 3 Opus",
            context_length=200000,
            prompt_price_1m=15.0,
            completion_price_1m=75.0,
            blended_price_1m=15.174,
            is_promo=False,
            output_modalities=["text"]
        )
    ]

    f_gemini = filter_catalog(dummy_catalog, query="gemini")
    assert len(f_gemini) == 1
    assert f_gemini[0].id == "google/gemini-2.5-flash-lite"

    f_promo = filter_catalog(dummy_catalog, promo_only=True)
    assert len(f_promo) == 1
    assert f_promo[0].id == "nvidia/nemotron-3.5-lightning:free"

    f_cheap = filter_catalog(dummy_catalog, filter_expressions=["price < 1.0"])
    assert len(f_cheap) == 3
    assert all(m.blended_price_1m < 1.0 for m in f_cheap)

    f_in = filter_catalog(dummy_catalog, max_input_price=0.15)
    assert len(f_in) == 2
