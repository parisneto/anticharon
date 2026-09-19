"""Tests for anticharon.tester.run_self_test's Mathematical Formula Verification
step (PE2-007). See docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-007.

All network calls are mocked (`requests.get` for the OpenRouter connectivity
check) and `ANTICHARON_CONFIG`/`ANTICHARON_DATA_DIR` point at an isolated
`tmp_path`, per this session's "do not depend on runtime data/" constraint.
"""

import json

from anticharon.tester import run_self_test


class _FakeModelsResponse:
    status_code = 200

    def json(self):
        return {"data": [{"id": "openai/gpt-5.6-luna"}]}


def _isolate(monkeypatch, tmp_path):
    cfg_path = tmp_path / "shortlist.json"
    cfg_path.write_text(json.dumps({"shortlist": []}), encoding="utf-8")
    monkeypatch.setenv("ANTICHARON_CONFIG", str(cfg_path))
    monkeypatch.setenv("ANTICHARON_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("anticharon.tester.requests.get", lambda *a, **kw: _FakeModelsResponse())


def test_run_self_test_math_engine_passes_with_canonical_implementation(monkeypatch, tmp_path):
    """Required regression test: 'Diagnostic passes with the canonical
    implementation.' Uses the real production calculate_effective_cost."""
    _isolate(monkeypatch, tmp_path)
    result = run_self_test(no_hermes=True, json_mode=True)
    assert result is True


def test_run_self_test_math_engine_zero_cache_reference_case_remains_correct(monkeypatch, tmp_path):
    """Required regression test: 'Zero-cache reference case remains correct.'
    Verified indirectly -- the zero-cache assertion lives inside run_self_test
    itself (Golden Case #4); this confirms it does not regress the overall
    diagnostic result when the cache-heavy case above it also runs."""
    _isolate(monkeypatch, tmp_path)
    assert run_self_test(no_hermes=True, json_mode=True) is True


def test_run_self_test_math_engine_fails_if_cache_read_pricing_ignored(monkeypatch, tmp_path, capsys):
    """Required regression test: 'Diagnostic fails or reports failure if
    cache-read pricing is ignored.' Simulates the exact PE2-007 regression --
    a calculate_effective_cost that silently prices cached tokens at the full
    uncached rate (the retired two-component formula's behavior) -- and
    confirms run_self_test now actually catches it, unlike the original
    hardcoded (1.0*0.99)+(2.0*0.01) check, which could never fail this way."""
    _isolate(monkeypatch, tmp_path)

    def broken_calculate_effective_cost(
        uncached_prompt_price_1m, cache_read_price_1m, completion_price_1m,
        uncached_tokens, cached_tokens, completion_tokens,
    ):
        # Legacy 2-component behavior: cached tokens priced as if uncached.
        return (
            (uncached_tokens + cached_tokens) / 1_000_000 * uncached_prompt_price_1m
            + completion_tokens / 1_000_000 * completion_price_1m
        )

    monkeypatch.setattr("anticharon.tester.calculate_effective_cost", broken_calculate_effective_cost)

    result = run_self_test(no_hermes=True, json_mode=True)
    captured = capsys.readouterr()
    diag = json.loads(captured.out)

    assert result is False
    assert diag["math_engine"]["verified"] is False
    assert "mismatch" in diag["math_engine"]["error"].lower()
