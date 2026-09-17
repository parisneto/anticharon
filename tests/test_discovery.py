"""Tests for anticharon.discovery's catalog fetch guard against sentinel pricing.

Only covers the negative-sentinel-price regression (see tests/test_pricing.py for
context). fetch_catalog() browses the *full* public catalog, so this is more
exposed than tracker.py's shortlist path -- a real user running
`anticharon model discover` would otherwise see openrouter/auto-beta ranked as
the globally cheapest model.
"""

import pytest

from anticharon.discovery import (
    CatalogModel,
    apply_zdr_filter,
    fetch_catalog,
    filter_catalog,
)


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


# --- PE2-002: missing/partial bulk-catalog pricing must never become a fabricated $0 ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-002.


def test_fetch_catalog_skips_model_missing_completion_field(monkeypatch):
    fake_data = [
        {
            "id": "broken/partial-pricing",
            "name": "Partial Pricing Model",
            "pricing": {"prompt": "0.000002"},  # completion entirely absent
        },
        {
            "id": "openai/gpt-5.6-luna",
            "name": "OpenAI: GPT-5.6 Luna",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
        },
    ]
    monkeypatch.setattr("anticharon.discovery.requests.get", lambda url, timeout=10.0: _FakeResponse(fake_data))

    catalog = fetch_catalog()
    ids = [m.id for m in catalog]
    assert "broken/partial-pricing" not in ids
    assert "openai/gpt-5.6-luna" in ids


def test_fetch_catalog_skips_model_with_empty_pricing_dict(monkeypatch):
    """Exact evidence scenario from PE2-002 in the full-catalog browse path:
    a model with `pricing={}` must never surface as a $0.0 "cheapest" model."""
    fake_data = [
        {"id": "broken/empty-pricing", "name": "Empty Pricing", "pricing": {}},
        {
            "id": "openai/gpt-5.6-luna",
            "name": "OpenAI: GPT-5.6 Luna",
            "pricing": {"prompt": "0.0000002", "completion": "0.0000012"},
        },
    ]
    monkeypatch.setattr("anticharon.discovery.requests.get", lambda url, timeout=10.0: _FakeResponse(fake_data))

    catalog = fetch_catalog()
    ids = [m.id for m in catalog]
    assert "broken/empty-pricing" not in ids
    assert catalog[0].blended_price_1m > 0  # the missing-pricing model never sorts first at $0


def test_fetch_catalog_keeps_legitimate_free_model(monkeypatch):
    """A real free model (explicit "0" for both fields) must remain in the catalog."""
    fake_data = [
        {"id": "some/free-model:free", "name": "Free Model", "pricing": {"prompt": "0", "completion": "0"}},
    ]
    monkeypatch.setattr("anticharon.discovery.requests.get", lambda url, timeout=10.0: _FakeResponse(fake_data))

    catalog = fetch_catalog()
    assert len(catalog) == 1
    assert catalog[0].blended_price_1m == 0.0
    assert catalog[0].is_promo is True


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


def test_fetch_catalog_has_no_zdr_param_and_does_not_live_check():
    """fetch_catalog() no longer performs any live ZDR check itself -- that's a
    separate, opt-in, post-filter step (apply_zdr_filter) so a live per-endpoint
    check only ever runs against an already-narrowed candidate list, not the
    full ~440-model catalog."""
    import inspect

    from anticharon import discovery

    params = inspect.signature(discovery.fetch_catalog).parameters
    assert "zdr_only" not in params


def _make_model(model_id: str, blended: float, canonical_slug: str = "") -> CatalogModel:
    return CatalogModel(
        id=model_id,
        name=model_id,
        context_length=100_000,
        prompt_price_1m=blended,
        completion_price_1m=blended,
        blended_price_1m=blended,
        is_promo=False,
        output_modalities=["text"],
        canonical_slug=canonical_slug or model_id,
    )


def test_apply_zdr_filter_excludes_unroutable_models(monkeypatch):
    models = [
        _make_model("openai/gpt-5.6-sol", 0.10, "openai/gpt-5.6-sol-20260709"),
        _make_model("azure-friendly/model", 0.20, "azure-friendly/model"),
    ]

    def fake_endpoints(canonical_slug, timeout=10.0):
        if canonical_slug == "azure-friendly/model":
            return [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}]
        return [{"provider_info": {"dataPolicy": {"retainsPrompts": True}}}]

    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", fake_endpoints)

    compliant, warning = apply_zdr_filter(models, max_check_count=10)
    ids = [m.id for m in compliant]
    assert "openai/gpt-5.6-sol" not in ids
    assert "azure-friendly/model" in ids
    assert warning is None


def test_apply_zdr_filter_checks_only_cheapest_n_and_warns_when_capped(monkeypatch):
    """Never silently truncate: exceeding max_check_count must both (a) only
    live-check the cheapest N candidates and (b) return a non-None warning."""
    models = [_make_model(f"provider/model-{i}", float(i), f"provider/model-{i}") for i in range(5)]
    checked_slugs = []

    def fake_endpoints(canonical_slug, timeout=10.0):
        checked_slugs.append(canonical_slug)
        return [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}]

    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", fake_endpoints)

    compliant, warning = apply_zdr_filter(models, max_check_count=2)

    # Only the 2 cheapest (model-0, model-1) were live-checked -- not all 5.
    assert set(checked_slugs) == {"provider/model-0", "provider/model-1"}
    assert len(compliant) == 2
    assert warning is not None
    assert "2 of 5" in warning
    assert "max_zdr_check_count" in warning


def test_apply_zdr_filter_no_warning_when_under_cap(monkeypatch):
    models = [_make_model("provider/model-0", 0.0, "provider/model-0")]
    monkeypatch.setattr(
        "anticharon.discovery.fetch_endpoint_policy_pricing",
        lambda canonical_slug, timeout=10.0: [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}],
    )
    compliant, warning = apply_zdr_filter(models, max_check_count=10)
    assert len(compliant) == 1
    assert warning is None


# --- PE2-003: policy lookup failure must be policy-unknown, not confirmed noncompliance ---
# See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-003.


def test_apply_zdr_filter_keeps_model_with_no_endpoint_data_as_unknown(monkeypatch):
    """A model whose endpoint fetch returns [] (timeout, HTTP error, malformed
    response, or genuinely no endpoints -- all indistinguishable by design) must
    be KEPT (routable-by-default), never dropped as if confirmed noncompliant."""
    models = [_make_model("provider/unknown-model", 0.10, "provider/unknown-model")]
    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", lambda *a, **kw: [])

    compliant, warning = apply_zdr_filter(models, max_check_count=10)
    assert len(compliant) == 1
    assert compliant[0].id == "provider/unknown-model"
    assert warning is not None
    assert "unknown" in warning.lower()
    assert "provider/unknown-model" in warning


def test_apply_zdr_filter_distinguishes_unknown_from_confirmed_noncompliant(monkeypatch):
    """Mixed candidates: one confirmed noncompliant (real endpoint data, none
    ZDR-compliant), one policy-unknown (no endpoint data at all), one confirmed
    compliant. Each must be handled according to its own distinct state."""
    models = [
        _make_model("provider/confirmed-noncompliant", 0.05, "provider/confirmed-noncompliant"),
        _make_model("provider/unknown", 0.10, "provider/unknown"),
        _make_model("provider/confirmed-compliant", 0.15, "provider/confirmed-compliant"),
    ]

    def fake_endpoints(canonical_slug, timeout=10.0):
        if canonical_slug == "provider/confirmed-noncompliant":
            return [{"provider_info": {"dataPolicy": {"retainsPrompts": True}}}]
        if canonical_slug == "provider/unknown":
            return []
        if canonical_slug == "provider/confirmed-compliant":
            return [{"provider_info": {"dataPolicy": {"retainsPrompts": False}}}]
        raise AssertionError(f"unexpected canonical_slug: {canonical_slug}")

    monkeypatch.setattr("anticharon.discovery.fetch_endpoint_policy_pricing", fake_endpoints)

    compliant, warning = apply_zdr_filter(models, max_check_count=10)
    ids = {m.id for m in compliant}
    assert ids == {"provider/unknown", "provider/confirmed-compliant"}
    assert "provider/confirmed-noncompliant" not in ids
    assert "provider/unknown" in warning


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
