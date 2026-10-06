"""EH-8 / D-9: the price is the cheapest standard-tier endpoint.

Tags and prices below are real shapes from OpenRouter (2026-10-06); expected values
are derived by hand from the default calibration 0.232622 / 0.764478 / 0.0029.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from anticharon.pricing import is_service_tier_tag, map_endpoint_tags
from anticharon.tracker import (
    resolve_policy_pricing,
    run_tracker,
    sync_effective_prices_for_model,
)

W = (0.232622, 0.764478, 0.0029)


def ep(tag, prompt, completion, cache=None, provider="X"):
    pricing = {"prompt": str(prompt / 1e6), "completion": str(completion / 1e6)}
    if cache is not None:
        pricing["input_cache_read"] = str(cache / 1e6)
    return {"tag": tag, "provider_name": provider, "pricing": pricing}


LUNA = [
    ep("openai/flex", 0.10, 0.60, 0.01, "OpenAI"),
    ep("azure", 0.20, 1.20, 0.02, "Azure"),
    ep("openai", 0.20, 1.20, 0.02, "OpenAI"),
    ep("amazon-bedrock/us-east-1", 0.22, 1.32, 0.022, "Amazon Bedrock"),
    ep("azure/eu", 0.22, 1.32, 0.022, "Azure"),
    ep("azure/us", 0.22, 1.32, 0.022, "Azure"),
    ep("openai/fast", 0.40, 2.40, 0.04, "OpenAI"),
]


@pytest.mark.parametrize("tag", [
    "openai", "azure", "azure/eu", "azure/us", "amazon-bedrock/us-east-1", "google-vertex/global",
    "google-vertex/eu", "relace/fp4", "streamlake/fp8", "deepinfra/bf16", "sail-research/us",
    "open-inference/zdr", "", None,
])
def test_standard_tags_are_not_service_tiers(tag):
    assert is_service_tier_tag(tag) is False


@pytest.mark.parametrize("tag", [
    "openai/flex", "openai/fast", "google-ai-studio/flex", "google-ai-studio/priority",
    "google-vertex/global/priority", "google-vertex/global/flex", "x/zdr/priority", "together/turbo",
    "provider/ultrafast", "provider/batch",
])
def test_service_tier_tags_are_detected_in_any_segment(tag):
    assert is_service_tier_tag(tag) is True


def test_luna_quote_is_the_standard_tier_not_the_flex_tier():
    result = resolve_policy_pricing(LUNA, *W, zdr_only=False)

    expected_standard = 0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2]  # 0.06529396
    expected_flex = 0.1 * W[0] + 0.01 * W[1] + 0.6 * W[2]  # 0.03264698, the old quote
    assert result["effective_price_1m"] == pytest.approx(expected_standard)
    assert result["effective_price_1m"] != pytest.approx(expected_flex)
    assert result["effective_endpoint_tag"] in {"azure", "openai"}
    assert result["only_non_standard_tiers"] is False


def test_gemini_quote_skips_flex_and_priority_but_keeps_vertex_global():
    gemini = [
        ep("google-ai-studio/flex", 0.125, 0.75, 0.0125), ep("google-vertex/global/flex", 0.125, 0.75, 0.0125),
        ep("google-ai-studio", 0.25, 1.50, 0.025), ep("google-vertex/global", 0.25, 1.50, 0.025),
        ep("google-vertex/eu", 0.275, 1.65, 0.0275), ep("google-ai-studio/priority", 0.45, 2.70, 0.045),
    ]
    result = resolve_policy_pricing(gemini, *W, zdr_only=False)
    assert result["effective_price_1m"] == pytest.approx(0.25 * W[0] + 0.025 * W[1] + 1.5 * W[2])  # 0.0816
    assert result["effective_endpoint_tag"] in {"google-ai-studio", "google-vertex/global"}


def test_model_with_only_tier_endpoints_falls_back_and_says_so():
    only_flex = [ep("openai/flex", 0.10, 0.60, 0.01), ep("openai/priority", 0.40, 2.40, 0.04)]
    result = resolve_policy_pricing(only_flex, *W, zdr_only=False)
    assert result["effective_price_1m"] == pytest.approx(0.1 * W[0] + 0.01 * W[1] + 0.6 * W[2])
    assert result["only_non_standard_tiers"] is True


def test_zdr_policy_price_also_excludes_tiers():
    flex = ep("openai/flex", 0.10, 0.60, 0.01)
    std = ep("azure", 0.20, 1.20, 0.02)
    for e in (flex, std):
        e["provider_info"] = {"dataPolicy": {"retainsPrompts": False}}
    result = resolve_policy_pricing([flex, std], *W, zdr_only=True)
    assert result["policy_price_1m"] == pytest.approx(0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2])


def _series(uuid, slug, i, o):
    return {"endpointId": uuid, "providerSlug": slug, "providerName": slug,
            "input": [{"at": "2026-09-05T00:00:00Z", "value": i}], "output": [{"at": "2026-09-05T00:00:00Z", "value": o}]}


def test_join_by_tag_prefix_maps_endpoints_that_provider_name_misses():
    endpoints = [ep("google-vertex/global", 0.25, 1.5, provider="Google"),
                 ep("google-vertex/global/flex", 0.125, 0.75, provider="Google"),
                 ep("google-ai-studio", 0.25, 1.5, provider="Google AI Studio")]
    series = [_series("u1", "google-vertex", 0.25, 1.5), _series("u2", "google-vertex", 0.125, 0.75),
              _series("u3", "google-ai-studio", 0.25, 1.5)]
    assert map_endpoint_tags(series, endpoints) == {
        "u1": "google-vertex/global", "u2": "google-vertex/global/flex", "u3": "google-ai-studio"}


def test_join_with_same_class_ambiguity_is_standard_and_differing_class_is_a_tier():
    same = map_endpoint_tags([_series("a", "azure", 0.22, 1.32)],
                             [ep("azure/eu", 0.22, 1.32), ep("azure/us", 0.22, 1.32)])
    differing = map_endpoint_tags([_series("b", "openai", 0.10, 0.60)],
                                  [ep("openai", 0.10, 0.60), ep("openai/flex", 0.10, 0.60)])
    assert not is_service_tier_tag(same["a"]) and same["a"] == "azure/eu"
    assert differing["b"] == "openai/flex"


def test_join_falls_back_to_input_then_output_when_a_price_moved_between_calls():
    series = [_series("x", "relace", 0.0134, 1.30), _series("y", "relace", 0.02, 1.28)]
    endpoints = [ep("relace/fp4", 0.0134, 1.28), ep("relace/flex", 0.05, 1.28)]
    mapped = map_endpoint_tags(series, endpoints)
    assert mapped["x"] == "relace/fp4"  # input price matches
    assert mapped["y"] == "relace/flex"  # only the output price matches; a tier tag wins ties


def test_unmatched_endpoints_are_omitted():
    assert map_endpoint_tags([_series("z", "nobody", 1.0, 1.0)], [ep("openai", 0.2, 1.2)]) == {}


NOW = datetime(2026, 9, 16, 10, 0, 0, tzinfo=timezone.utc)
WEIGHTS = W


def _listed(*items):
    return {"series": list(items)}


def test_history_excludes_the_flex_endpoint_and_keeps_the_standard_one(monkeypatch):
    std = _series("std-uuid", "openai", 0.20, 1.20)
    flex = _series("flex-uuid", "openai", 0.10, 0.60)
    for item, cache in ((std, 0.02), (flex, 0.01)):
        item["cacheRead"] = [{"at": "2026-09-05T00:00:00Z", "value": cache}]
    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: _listed(std, flex))
    endpoints = [ep("openai", 0.20, 1.20), ep("openai/flex", 0.10, 0.60)]
    store = {}

    sync_effective_prices_for_model("openai/m", "openai/m-1", store, WEIGHTS, 5.0, now=NOW, endpoints=endpoints)

    entry = store["openai/m"]
    assert entry["endpoint_tags"] == {"std-uuid": "openai", "flex-uuid": "openai/flex"}
    expected = 0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2]  # standard tier, not the cheaper flex 0.03265
    assert [o["effective_price_1m"] for o in entry["observations"]] == [pytest.approx(expected)] * len(entry["observations"])
    assert entry["basis"] == "listed_blend" and entry["weights_used"] == list(W)


def test_stored_tags_keep_a_removed_endpoint_excluded_and_nothing_is_derived_without_tags(monkeypatch):
    flex = _series("flex-uuid", "openai", 0.10, 0.60)
    std = _series("std-uuid", "openai", 0.20, 1.20)
    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: _listed(std, flex))
    store = {"openai/m": {"canonical_slug": "openai/m-1", "endpoint_tags": {"flex-uuid": "openai/flex"}}}

    sync_effective_prices_for_model("openai/m", "openai/m-1", store, WEIGHTS, 5.0, now=NOW)  # endpoints route failed

    # The stored map still classifies the removed flex endpoint; the standard one is kept.
    prices = [o["effective_price_1m"] for o in store["openai/m"]["observations"]]
    assert prices and all(p == pytest.approx(0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2]) for p in prices)

    blank = {}
    sync_effective_prices_for_model("openai/n", "openai/n-1", blank, WEIGHTS, 5.0, now=NOW)  # no tags, no endpoints
    assert "observations" not in blank["openai/n"] or blank["openai/n"]["observations"] == []
    assert blank["openai/n"].get("basis") is None  # tiers could not be excluded, so no history is derived


def test_run_reports_the_standard_quote_the_endpoint_tag_and_the_only_tier_warning(monkeypatch, tmp_path):
    cfg = tmp_path / "shortlist.json"
    cfg.write_text(json.dumps({"shortlist": [{"model": "acme/std", "source": "manual", "order": 0},
                                             {"model": "acme/onlyflex", "source": "manual"}]}), encoding="utf-8")
    catalog = {m: {"id": m, "canonical_slug": f"{m}-1", "pricing": {"prompt": "0.0000002", "completion": "0.0000012"}}
               for m in ("acme/std", "acme/onlyflex")}
    monkeypatch.setattr("anticharon.tracker.fetch_openrouter_models", lambda timeout=10.0: catalog)
    endpoints = {"acme/std-1": LUNA, "acme/onlyflex-1": [ep("x/flex", 0.10, 0.60, 0.01)]}
    monkeypatch.setattr("anticharon.tracker.fetch_endpoint_policy_pricing", lambda slug, *a, **k: endpoints[slug])
    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: {})
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))

    result = run_tracker(dry_run=True, config_path=cfg, history_path=tmp_path / "history.csv", no_hermes=True)

    rows = {p.model: p for p in result.prices_shortlist}
    assert rows["acme/std"].price_1m == pytest.approx(0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2])
    assert rows["acme/std"].price.endpoint_tag in {"azure", "openai"}
    assert rows["acme/std"].to_dict()["endpoint_tag"] in {"azure", "openai"}
    codes = [(m.code, m.model) for m in result.messages]
    assert ("ONLY_NON_STANDARD_TIERS", "acme/onlyflex") in codes
    assert not [c for c in codes if c == ("ONLY_NON_STANDARD_TIERS", "acme/std")]


# --- Real frontend `/stats/endpoint` shape: the tag lives in `provider_slug`, not `tag` ---

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_endpoints(name):
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))["data"]
    return data if isinstance(data, list) else data["endpoints"]


def test_real_luna_fixture_uses_provider_slug_as_the_tag():
    endpoints = _fixture_endpoints("openrouter_endpoint_stats_gpt-5.6-luna_trimmed.json")
    assert all("tag" not in e and e["provider_slug"] for e in endpoints)  # the shape that broke the VM run

    result = resolve_policy_pricing(endpoints, *W, zdr_only=False)

    assert result["effective_price_1m"] == pytest.approx(0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2])  # 0.06529, not the flex 0.03265
    assert result["effective_endpoint_tag"] in {"azure", "openai"}


def test_frontend_shape_gemini_tags_from_the_live_route():
    gemini = [{"provider_slug": slug, "provider_name": "Google",
               "pricing": {"prompt": str(p / 1e6), "completion": str(c / 1e6), "input_cache_read": str(cr / 1e6)}}
              for slug, p, c, cr in [
                  ("google-vertex/global/flex", 0.125, 0.75, 0.0125), ("google-ai-studio/flex", 0.125, 0.75, 0.0125),
                  ("google-ai-studio", 0.25, 1.5, 0.025), ("google-vertex/global", 0.25, 1.5, 0.025),
                  ("google-vertex/eu", 0.275, 1.65, 0.0275), ("google-vertex/global/priority", 0.45, 2.7, 0.045)]]

    result = resolve_policy_pricing(gemini, *W, zdr_only=False)

    assert result["effective_price_1m"] == pytest.approx(0.25 * W[0] + 0.025 * W[1] + 1.5 * W[2])  # 0.08162
    assert result["effective_endpoint_tag"] in {"google-ai-studio", "google-vertex/global"}


def test_tag_join_works_with_frontend_shaped_endpoints_and_the_real_listed_fixture(monkeypatch):
    endpoints = _fixture_endpoints("openrouter_endpoint_stats_gpt-5.6-luna_trimmed.json")
    listed = json.loads((FIXTURES / "openrouter_listed_pricing_gpt-5.6-luna_trimmed.json").read_text(encoding="utf-8"))["data"]
    tags = map_endpoint_tags(listed["series"], endpoints)

    assert sorted(tags.values()) == sorted(
        ["openai/fast", "azure", "amazon-bedrock/us-east-1", "azure/eu", "azure/eu", "openai", "openai/flex"])
    assert tags["297a2285-308d-4bfb-a120-a9c2ead800b0"] == "openai/fast"
    assert tags["ff94b1f1-db76-42c5-a21e-06083c3cc7d0"] == "openai/flex"

    monkeypatch.setattr("anticharon.tracker.fetch_listed_pricing", lambda *a, **k: listed)
    store = {}
    sync_effective_prices_for_model("openai/gpt-5.6-luna", "openai/gpt-5.6-luna-20260709", store, WEIGHTS, 5.0,
                                    now=NOW, endpoints=endpoints)
    standard = 0.2 * W[0] + 0.02 * W[1] + 1.2 * W[2]  # 0.06529396, independently computed
    observations = store["openai/gpt-5.6-luna"]["observations"]
    assert observations[0]["date"] == "2026-09-05" and observations[-1]["date"] == "2026-09-16"
    assert all(o["effective_price_1m"] == pytest.approx(standard) for o in observations)
