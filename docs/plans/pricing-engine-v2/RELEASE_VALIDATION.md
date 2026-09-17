# Pricing Engine v2 — Release Validation

## Validation Target

- Initiative: Pricing Engine v2
- Feature branch: `pricing-engine-v2`
- Base branch: `main`
- Originally assessed commit: `90aaa06f5b1866b98d0a4463794ed00933a62f0a`
- Current remediation HEAD: `c112b2c8ae95cbd3e979d2bc3b68d9e1683e4d03`
- Originally assessed version: `v0.5.2`
- Initial validation date: `2026-09-16`
- Reviewer: Codex
- Overall status: `BLOCKED`

The current remediation HEAD has not yet received independent validation. Test
results reported by the remediation agent are recorded as implementation
evidence, not final release evidence.

## Scope and Sources

This validation cross-checks implementation, tests, documentation, and release
state against:

- `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`
- `docs/plans/pricing-engine-v2/PLAN.md`
- `docs/plans/pricing-engine-v2/ADR_CANDIDATE_TOKENS_CACHED.md`
- `docs/specs/spec_v1_anticharon.md`
- `AGENTS.md`
- `CHANGELOG.md`
- `README.md`
- `.github/workflows/ci.yml`
- `pyproject.toml`

The Execution Contract is authoritative. `PLAN.md` provides the detailed design.
The candidate ADR and empirical artifacts provide supporting evidence.

## Repository State

### Initial assessment

- Feature commit: `90aaa06f5b1866b98d0a4463794ed00933a62f0a`
- Feature worktree: clean
- Runtime `data/`: excluded from inspection
- Tests ran in a disposable checkout with an isolated `.venv`, dependency cache,
  and runtime-data directory.

### Current remediation state

- Remediation HEAD: `c112b2c8ae95cbd3e979d2bc3b68d9e1683e4d03`
- PE2-001 implementation commit: `70fe99bf540ef8f233bc6db373797b299eb93547`
- PE2-001 ledger commit: `c112b2c8ae95cbd3e979d2bc3b68d9e1683e4d03`
- Reported divergence after remediation: 12 commits ahead and 0 behind `main`
- Reported worktree state: clean
- Independent confirmation: pending

## Initial Verification Results

| Gate | Result | Evidence |
|---|---|---|
| Offline pytest | PASS | 86 passed, 3 deselected in 2.24s |
| Live pytest | PASS | 3 passed, 86 deselected in 10.37s |
| CLI diagnostic | PASS | OpenRouter reachable; 444 models reported |
| Manual normal-versus-ZDR check | FAIL | Effective/policy collapse and unroutable recommendation reproduced |
| `git diff --check` | PASS | No whitespace errors |
| Ruff | FAIL | 245 repository-wide findings |
| Release decision | BLOCKED | P1/P2 findings remained |

## Findings

### PE2-001 — Effective and policy prices collapse under ZDR

- Severity: P1
- Status: `Ready for Retest`
- Contract impact:
  - Three-price distinction
  - Policy-constrained recommendations
  - Consistent downstream calculations
  - Non-misleading user-visible output
- Affected files:
  - `src/anticharon/tracker.py`
  - `src/anticharon/models.py`
  - `tests/test_tracker.py`
  - `docs/specs/spec_v1_anticharon.md`
- Original evidence:
  - Normal `openai/gpt-5.6-luna` effective price: approximately `$0.03267/1M`.
  - Under `--zdr`, `effective_price_1m` changed to approximately `$0.06534/1M`,
    which was the policy price.
  - The normal run classified the current price as a drop, while the ZDR run
    classified it as a spike against the same unconstrained history.
  - `qwen/qwen3.7-flash` reported `is_policy_routable=false` but was still sorted
    first and emitted `BEST_OPTION_CHANGED`.
- Root cause:
  - `run_tracker()` used a single display value that switched between effective
    and policy pricing.
  - That value was reused for serialization, sorting, alerts, and recommendations.
  - Policy-constrained current pricing was compared with unconstrained historical
    moving averages.
- Required correction:
  - Preserve effective and policy prices independently.
  - Never serialize a policy price as `effective_price_1m`.
  - Compare historical effective prices only with current effective prices unless
    a separate compatible policy-price history is introduced.
  - Never recommend a confirmed policy-unroutable model under an active policy.
  - Preserve a semantic distinction between confirmed unroutable and
    policy-unknown.
- Required regression tests:
  - Effective and policy prices remain separately visible under `--zdr`.
  - Enabling policy output does not alter `effective_price_1m`.
  - Policy-unroutable models cannot trigger `BEST_OPTION_CHANGED`.
  - Effective-price alerts remain like-for-like with effective-price history.
  - Policy-routable, policy-unroutable, and policy-unknown states remain distinct.
  - A policy-unknown model is handled according to the contract’s explicit
    graceful-degradation rule.
- Implementation evidence:
  - Implementation commit: `70fe99b`
  - Ledger commit: `c112b2c`
  - `ModelPrice.price_1m` now remains the unconstrained effective price.
  - Serialization reads the effective value from `PricePoint`.
  - Policy-aware ranking uses a separate helper.
  - Confirmed policy-unroutable models are ranked after routable models.
  - Specification and changelog were updated.
  - Three regression tests were added.
- Remediation-agent verification:
  - `uv run pytest`: 89 passed, 3 deselected.
  - `uv run pytest -m live`: 3 passed, 89 deselected.
  - `uv run anticharon test`: reported passing.
  - Manual normal-versus-ZDR comparison: reported passing.
- Independent-retest requirement:
  - Verify all remediation claims at the exact remediation commit.
  - Specifically verify whether treating both policy-unroutable and
    policy-unknown prices as an infinite ranking value conflicts with the plan’s
    “policy-unknown, routable-by-default” degradation rule.
- Independent retest:
  - Pending

### PE2-002 — Missing or partial pricing becomes a valid zero-cost endpoint

- Severity: P1
- Status: `Ready for Retest`
- Contract impact:
  - Missing/partial pricing fallback
  - Provider-level price correctness
  - Sorting and recommendations
  - Historical-data integrity
- Affected files:
  - `src/anticharon/tracker.py`
  - `src/anticharon/discovery.py`
  - `tests/test_tracker.py`
  - `tests/test_policy_pricing.py`
  - `tests/test_discovery.py`
- Evidence:
  - Endpoint parsing defaults absent `pricing.prompt` and
    `pricing.completion` values to zero.
  - Zero is a legitimate OpenRouter free-price value, so absence and genuine
    zero become indistinguishable.
  - A targeted probe using an endpoint with `pricing={}` returned:

    ```text
    effective_price_1m = 0.0
    policy_price_1m = 0.0
    is_policy_routable = true
    ```

  - Such an endpoint can become the cheapest provider, influence recommendations,
    and persist false zero pricing.
- Required correction:
  - Distinguish absent, blank, malformed, and partial required pricing fields from
    genuine numeric zero.
  - Reject or explicitly fall back from endpoints missing required prompt or
    completion pricing.
  - Never fabricate a free endpoint from missing data.
  - Apply consistent validation to tracker and discovery paths.
- Required regression tests:
  - Missing prompt field.
  - Missing completion field.
  - Both fields missing.
  - Blank prompt or completion.
  - Malformed numeric values.
  - Legitimate numeric zero.
  - Mixed malformed and valid endpoints.
  - All endpoints malformed.
  - Bulk-catalog partial-pricing fallback.
- Implementation evidence:
  - `src/anticharon/pricing.py` gains `parse_required_price_1m(pricing, field)`,
    returning `None` (never `0.0`) for a missing key, `None` value, blank
    string, or non-numeric value; a genuine `"0"` still parses as a real `0.0`.
    Live-verified 2026-09-17 that every real bulk-catalog model and every real
    per-endpoint entry (including genuine free `:free` models) always includes
    both `prompt` and `completion` as present keys — never by omission — so
    requiring presence does not risk rejecting a real free model.
  - `src/anticharon/tracker.py`'s `_endpoint_blended_rate_1m()` (per-endpoint
    pricing) and `run_tracker()`'s bulk-catalog advertised-price parsing both
    now use `parse_required_price_1m()` and skip the endpoint/model entirely
    (rather than pricing it at `$0`) when either required field is missing.
  - `src/anticharon/discovery.py`'s `fetch_catalog()` uses the same helper and
    skips the catalog model entirely under the same condition.
  - Reconciliation discovered while writing PE2-002's regression tests, fixed
    in the same commit: `resolve_policy_pricing()` (`tracker.py`) previously
    gated `is_policy_routable`/`policy_price_1m` on whether the raw `endpoints`
    list was non-empty, not on whether any endpoint actually produced a usable
    price via `_endpoint_blended_rate_1m()`. A non-empty `endpoints` list where
    every entry has missing/malformed pricing (this finding's exact scenario)
    was therefore reported as `is_policy_routable=false` ("confirmed
    unroutable") instead of `is_policy_routable=None` ("policy-unknown") —
    the same class of defect PE2-003 describes for the fetch layer, found here
    one level down in the resolution layer. Fixed by gating on `rates` (the
    list of endpoints that actually parsed) instead of `endpoints`.
  - `docs/specs/spec_v1_anticharon.md` §3.1a documents the required-field rule
    and the distinction from `input_cache_read`'s legitimate optional-with-
    fallback status.
  - Regression tests added, one per required-tests bullet above:
    `tests/test_pricing.py` (7 unit tests on `parse_required_price_1m` itself:
    missing field, both fields missing, null value, blank string, malformed
    value, legitimate zero, real value), `tests/test_policy_pricing.py` (6:
    the exact `pricing={}` evidence scenario, missing completion, blank
    prompt, mixed malformed+valid, all endpoints malformed, legitimate zero
    endpoint), `tests/test_tracker.py` (2: missing bulk-catalog field skips
    the model end-to-end, the exact evidence scenario reproduced through
    `run_tracker` end-to-end), `tests/test_discovery.py` (3: missing field,
    empty pricing dict, legitimate free model kept).
- Remediation-agent verification:
  - `uv run pytest`: 107 passed, 3 deselected.
  - Manual: reproduced normal (non-degenerate) operation live against
    `openai/gpt-5.6-luna` + `qwen/qwen3.7-flash` in an isolated temp data dir —
    confirmed both models' `effective_price_1m` unchanged from pre-fix values
    ($0.03265 / $0.01194), i.e. the fix does not alter real pricing for real
    endpoints. The exact `pricing={}` scenario itself cannot be forced against
    the live API (OpenRouter does not serve malformed pricing on demand) --
    covered by the unit/fixture/mocked-integration tests above instead, per
    the Execution Contract's trust hierarchy (pure logic → known payload →
    mocked flow → failure fallback → optional live API).
  - `git diff --check`: clean.
  - `ruff`: zero new findings introduced (verified line-by-line against the
    diff hunks in all three touched source files; `pricing.py`'s new code has
    zero findings, and the findings ruff reports on `tracker.py`/`discovery.py`
    are all on lines this change did not modify).
- Resolution commit: `8cccc19`
- Independent retest:
  - Pending

### PE2-003 — Policy lookup failure is treated as confirmed noncompliance

- Severity: P1
- Status: `Ready for Retest`
- Contract impact:
  - Graceful degradation
  - Policy-unknown behavior
  - Discovery correctness
  - Non-misleading filtering
- Affected files:
  - `src/anticharon/discovery.py`
  - `src/anticharon/tracker.py`
  - `tests/test_discovery.py`
  - `tests/test_tracker.py`
- Evidence:
  - `fetch_endpoint_policy_pricing()` returns an empty list for timeout, HTTP
    failure, malformed response, or genuinely absent endpoint data.
  - `apply_zdr_filter()` treats the empty result as “not compliant” and removes
    the model.
  - The plan requires internal-route failure to become policy-unknown and
    routable-by-default rather than fabricated noncompliance.
  - PE2-001’s remediation may also rank policy-unknown models identically to
    confirmed unroutable models; this must be reconciled here.
- Required correction:
  - Represent endpoint-fetch outcome separately from the endpoint list.
  - Distinguish:
    - confirmed compliant;
    - confirmed noncompliant;
    - policy unknown because retrieval or parsing failed.
  - Follow one documented graceful-degradation rule consistently across tracker,
    discovery, CLI, JSON, and MCP surfaces.
  - Surface uncertainty explicitly.
- Required regression tests:
  - Timeout.
  - Connection failure.
  - HTTP error.
  - Malformed JSON.
  - Wrong response shape.
  - Empty successful response.
  - Confirmed compliant endpoint.
  - Confirmed noncompliant endpoints.
  - Mixed endpoints.
  - Policy-unknown serialization and discovery output.
  - Policy-unknown ranking behavior.
- Implementation evidence:
  - Design decision: `fetch_endpoint_policy_pricing()`'s return contract is
    unchanged (`[]` on any failure) -- its existing broad `except Exception`
    already normalizes timeout, connection error, HTTP error, malformed JSON,
    and wrong-response-shape into one signal, verified directly with 6 new
    mocked tests in `tests/test_network_failure_paths.py`. A genuinely
    successful response reporting zero endpoints produces the same `[]`
    signal. All of these mean "no real endpoint pricing data exists," so they
    are deliberately treated identically by every downstream consumer, rather
    than introducing a separate typed fetch-outcome signal that would carry
    no additional decision-relevant information for this codebase's actual
    behavior contract.
  - `src/anticharon/discovery.py`'s `apply_zdr_filter()`: a candidate whose
    endpoint fetch returns `[]` is now **kept** (routable-by-default) instead
    of dropped as unroutable; the returned warning names which candidates
    were kept this way, distinct from the existing cap-truncation warning.
  - `src/anticharon/tracker.py`'s `_rank_price_1m()` (introduced by PE2-001):
    reconciled per PE2-001's own flagged independent-retest requirement.
    Three distinct outcomes now: `policy_price_1m` set → rank by it;
    `is_policy_routable is False` (confirmed unroutable) → rank `math.inf`,
    never recommended; `is_policy_routable is None` (unknown) →
    routable-by-default, rank by the unconstrained effective price, CAN be
    recommended. Previously the last two shared the `math.inf` outcome.
  - New `PriceWarning` type `POLICY_UNKNOWN` (`models.py` already supported
    arbitrary `type` strings; no schema change needed) fires in `run_tracker`
    whenever `zdr_only` is active and `is_policy_routable is None`, distinct
    from `POLICY_UNROUTABLE`. Wired into CLI human-output formatting
    (`cli.py`) alongside the existing `POLICY_UNROUTABLE` handling; already
    present in `--json`/MCP output via the existing `PriceWarning.to_dict()`
    (no change needed there, since it already serializes `type`/`message`/
    `policy`/`reason` generically).
  - Also corrected a stale `docs/specs/spec_v1_anticharon.md` §3.7 line,
    found while updating this section, that claimed `Policy_Price_1M`
    replaces `Effective_Price_1M` in `Delta_7d_Pct` under an active policy
    filter -- a leftover from before PE2-001's fix that should have been
    removed then but wasn't; it directly contradicted PE2-001's own
    (correct, tested) resolution.
  - Regression tests added: `tests/test_network_failure_paths.py` (7, direct
    coverage of `fetch_endpoint_policy_pricing`'s failure normalization:
    timeout, connection error, HTTP error, malformed JSON, wrong shape,
    empty success, real success), `tests/test_discovery.py` (2: unknown
    model kept with a descriptive warning, three-way mix of
    confirmed-noncompliant/unknown/confirmed-compliant each handled
    correctly), `tests/test_tracker.py` (2: `POLICY_UNKNOWN` fires instead
    of `POLICY_UNROUTABLE` for unknown models, and a policy-unknown model
    can win `BEST_OPTION_CHANGED` while a confirmed-unroutable one still
    cannot -- the existing PE2-001 test for that case, unchanged, still
    passes).
- Remediation-agent verification:
  - `uv run pytest`: 118 passed, 3 deselected.
  - `uv run pytest -m live`: 3 passed, 118 deselected.
  - Manual: live-verified `model discover "sol-pro" --zdr` and
    `check --zdr` against the real API still behave correctly for the
    confirmed-compliant/confirmed-noncompliant cases (unchanged from
    PE2-001's manual verification); the `POLICY_UNKNOWN` path itself cannot
    be forced against the live API (OpenRouter does not serve fetch failures
    on demand) -- covered by the mocked tests above instead, per the
    Contract's trust hierarchy.
  - `git diff --check`: clean.
  - `ruff`: one genuinely new finding disclosed, not hidden: `UP006` on
    `discovery.py`'s new `unknown_model_ids: List[str] = []` line -- it uses
    the same legacy `typing.List` style as 100% of the pre-existing code in
    that file (including the adjacent, unmodified `compliant: List[...]`
    line immediately above it). Following the file's own established
    convention was judged preferable to introducing a mixed style within one
    function; the broader legacy-typing-style question across the whole
    codebase is PE2-010's scope, not this finding's. All other touched files
    (`tracker.py`, `cli.py`) introduced zero new findings.
- Resolution commit: `eaef6dd`
- Independent retest:
  - Pending

### PE2-004 — Granular historical persistence does not match the plan

- Severity: P2
- Status: `Ready for Retest`
- Contract impact:
  - Provider-specific pricing representation
  - Local storage/schema requirements
  - Historical evidence fidelity
  - Plan/specification synchronization
- Affected files:
  - `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`
  - `docs/plans/pricing-engine-v2/PLAN.md`
  - `docs/specs/spec_v1_anticharon.md`
  - `src/anticharon/storage.py`
  - `src/anticharon/tracker.py`
  - `tests/test_storage.py`
  - `tests/test_effective_pricing_backfill.py`
- Evidence:
  - `PLAN.md` describes a per-model, per-provider daily time series containing,
    where available:
    - date;
    - provider;
    - effective price;
    - listed price;
    - cache-hit rate;
    - token share.
  - `_reduce_to_daily_observations()` immediately collapses all providers into
    one minimum price per day.
  - `effective_prices.json` stores only records equivalent to:

    ```json
    {
      "date": "2026-09-15",
      "effective_price_1m": 0.05
    }
    ```

  - Provider identity and other planned dimensions are irreversibly discarded.
  - The specification was changed to describe the reduced implementation without
    synchronizing the authoritative plan and contract.
- Required decision:
  - Either implement the required provider-granular store, or formally narrow
    the architecture by synchronizing:
    - Execution Contract;
    - Plan;
    - specification;
    - ADR material;
    - validation artifact.
  - Do not silently redefine completion to match existing code.
- Required regression tests:
  - Final documented granular schema round-trip.
  - Multiple providers on the same date.
  - Deterministic summary derivation.
  - Provider identity preservation or an explicitly approved reduction rule.
  - Duplicate refresh/idempotency behavior.
  - Partial provider data.
  - No fabricated observations.
- Decision made (not silently chosen -- recorded per the task's reconciliation
  requirement, flagged for user awareness as a scope/design decision):
  - **Narrowed the architecture, did not implement full provider-granular
    persistence.** `EXECUTION_CONTRACT.md`'s actual Storage acceptance
    criteria ("the newly required pricing dimensions and the 28-day
    historical observations needed by downstream calculations") never itself
    required provider-level granularity in the persisted store -- that
    specificity was `PLAN.md`'s own elaboration, never promoted into the
    Contract's criteria. No downstream calculation in this codebase (history
    derivation, analytics profiles, `NEWLY_TRACKED` threshold) consumes
    per-provider history; all only need the single cheapest-per-day blended
    price already provided. Per `EXECUTION_CONTRACT.md` §4's own Non-Goals
    ("concrete over general... do not solve adjacent discoveries unless
    required by the defined outcome"), implementing full provider-granular
    persistence with zero current consumers would itself have been the kind
    of premature generalization this initiative explicitly rules out.
  - Documents reconciled: `PLAN.md`'s "Storage architecture" section now
    carries an explicit "Scope correction" note describing what was
    originally envisioned, what shipped instead, and why; `EXECUTION_CONTRACT.md`'s
    Deferred section now has a real entry for provider-granular persistence
    (previously only placeholder text); `docs/specs/spec_v1_anticharon.md`
    §5.2's heading, which incorrectly said "per-model, per-provider daily
    observations" (never matching the schema documented directly below it),
    is corrected. `ADR_CANDIDATE_TOKENS_CACHED.md` was checked and does not
    make any provider-granular-persistence claim -- no edit needed there.
  - Also resolved as a side effect of editing the same `PLAN.md` paragraph:
    the "Exact cadence **OPEN**" marker PE2-009 separately flags as
    contradicting revision 3's "no remaining open decisions" claim -- the
    actual shipped cadence (24-hour staleness, `DEFAULT_EFFECTIVE_PRICES_STALE_HOURS`
    in `storage.py`) is now documented in place of the stale marker.
    Cross-referenced in PE2-009's own entry below.
- Implementation evidence:
  - `src/anticharon/storage.py`/`tracker.py` are unchanged by this finding --
    the "Final documented granular schema round-trip" regression test
    requirement is satisfied by the existing, unmodified
    `tests/test_storage.py::test_effective_prices_store_roundtrip`, which
    already round-trips the actual (now formally documented) schema exactly.
  - New regression test added to lock in the reduction rule as an approved
    decision, not an oversight (the "Provider identity preservation or an
    explicitly approved reduction rule" requirement):
    `tests/test_effective_pricing_backfill.py::test_reduce_to_daily_observations_provider_identity_is_intentionally_discarded`
    -- given three different providers priced on the same day, asserts the
    stored observation is exactly `{date, effective_price_1m}` (no provider
    key) and that the cheapest of the three wins.
  - "Multiple providers on the same date," "duplicate refresh/idempotency
    behavior," "partial provider data," and "no fabricated observations"
    were already covered by pre-existing tests before this finding was
    opened (`test_reduce_to_daily_observations_picks_cheapest_endpoint_per_day`,
    `test_sync_effective_prices_for_model_preserves_prior_data_on_transient_failure`,
    `test_reduce_to_daily_observations_skips_endpoint_missing_output_side`,
    and the broader no-fabrication tests across `test_storage.py`) --
    verified they exist and pass, no gap found requiring a new test.
- Remediation-agent verification:
  - `uv run pytest`: 119 passed, 3 deselected.
  - `git diff --check`: clean.
  - `ruff`: zero new findings (this finding's changes are pure Markdown docs
    plus one new pure-Python test function using the same style as its
    neighbors in an already-clean file).
- Resolution commit: `a2c5c71`
- Independent retest:
  - Pending

### PE2-005 — Live backfill canary does not perform the promised cross-validation

- Severity: P2
- Status: `Ready for Retest`
- Contract impact:
  - Live API contract validation
  - Public-versus-internal price consistency
  - Detection of external semantic drift
- Affected files:
  - `tests/test_effective_pricing_backfill.py`
  - `docs/plans/pricing-engine-v2/PLAN.md`
- Evidence:
  - The plan requires the internal effective-pricing route’s listed baseline to
    match the public catalog’s listed price for the same model and day.
  - The live test only asserts:

    ```text
    cheapest_effective_input ≤ advertised_prompt_price × 1.5
    ```

  - It does not extract the internal listed baseline.
  - It does not compare like-for-like listed values.
  - A substantial payload or semantic change can pass.
- Required correction:
  - Extract comparable listed-price values from both sources.
  - Define and document a tolerance based on source precision and timing.
  - Fail when the internal route changes shape or listed-price semantics.
  - Keep the test explicitly marked `@pytest.mark.live`.
- Required regression tests:
  - Deterministic fixture test for internal listed-price extraction.
  - Live same-model/same-day baseline comparison.
  - Missing listed baseline.
  - Changed payload shape.
- Investigation finding, reconciled under this ID: live-verified 2026-09-17
  that the internal effective-pricing route (`/stats/effective-pricing`) has
  no raw listed-price field at all in its current shape -- only cache-
  weighted `effectiveInputPrice`/`effectiveOutputPrice` per provider and
  aggregate `weightedInputPrice`/`weightedOutputPrice`. `PLAN.md`'s original
  design for this canary assumed a field that does not exist, so "extract
  comparable listed-price values from both sources" could not be satisfied
  as originally specified against that pairing of routes.
- Implementation evidence:
  - Corrected design: compare the bulk catalog's `advertised_prompt_1m`
    against the raw per-endpoint listed prices from `/stats/endpoint`
    instead (the route `fetch_endpoint_policy_pricing` already uses
    elsewhere in this codebase for policy/effective pricing) -- the bulk
    catalog's headline is definitionally one of those endpoints' own listed
    price, so at least one should match it exactly. Live-verified: 2 of 7
    endpoints matched exactly for `openai/gpt-5.6-luna`.
  - New `src/anticharon/tracker.py::extract_endpoint_listed_prices_1m()`:
    pure extraction function, reuses `parse_required_price_1m`/
    `is_valid_listed_price` (PE2-002) so malformed/sentinel endpoint pricing
    is already excluded consistently with the rest of the codebase.
  - Tolerance defined and documented (the "define and document a tolerance"
    requirement): a tight float-rounding allowance (`abs(diff) < 1e-6`), not
    a loose multiplier -- the previous `<= 1.5x` check could pass even after
    a real semantic drift between the routes, which is exactly the failure
    mode this canary exists to catch.
  - `tests/test_effective_pricing_backfill.py::test_effective_pricing_cross_validation_canary`
    (`@pytest.mark.live`) rewritten to the corrected design; live-run and
    confirmed passing against the real API.
  - `docs/plans/pricing-engine-v2/PLAN.md`'s "28-Day Backfill" section
    ("Gated cross-validation test") and "Verification" section corrected to
    describe the actual comparison being made.
  - Regression tests added, deterministic (no network):
    `test_extract_endpoint_listed_prices_1m_basic` (the "deterministic
    fixture test for internal listed-price extraction" requirement --
    "internal" here now correctly means `/stats/endpoint`, the route that
    actually has listed prices, not `/stats/effective-pricing`),
    `test_extract_endpoint_listed_prices_1m_missing_listed_baseline_returns_empty`
    (the "missing listed baseline" requirement), and
    `test_extract_endpoint_listed_prices_1m_skips_sentinel_prices` (the
    "changed payload shape" requirement, applied to a real shape variant
    already seen live -- a meta-router's `"-1"` sentinel pricing).
- Remediation-agent verification:
  - `uv run pytest`: 122 passed, 3 deselected.
  - `uv run pytest -m live`: 3 passed, 122 deselected -- including the
    rewritten canary itself, confirmed passing against the real API today.
  - `uv run anticharon test`: PASS.
  - `git diff --check`: clean.
  - `ruff`: two new findings disclosed, not hidden: `UP006` on the new
    `extract_endpoint_listed_prices_1m()` function's signature and its
    `prices: List[float] = []` body line -- both match this file's 100%
    pre-existing legacy `typing.List`/`typing.Dict` style throughout (same
    judgment call as PE2-003's disclosed finding on `discovery.py`).
- Resolution commit: `4006f2e`
- Independent retest:
  - Pending

### PE2-006 — Mandatory failure-path and realistic-payload coverage is incomplete

- Severity: P2
- Status: `Ready for Retest`
- Contract impact:
  - Mature test-suite requirements
  - Deterministic failure handling
  - External-payload regression detection
  - Mocked integration coverage
- Affected files:
  - `tests/test_tracker.py`
  - `tests/test_discovery.py`
  - `tests/test_policy_pricing.py`
  - `tests/test_effective_pricing_backfill.py`
  - `tests/test_cli.py`
  - `tests/test_mcp.py`
  - `tests/fixtures/`
- Evidence:
  - The deterministic suite lacks complete tests for:
    - request timeout;
    - connection failure;
    - non-2xx endpoint/history responses;
    - malformed JSON;
    - incorrect response shape;
    - missing/partial endpoint prices;
    - policy lookup failure during discovery;
    - policy-unknown output;
    - effective-versus-policy preservation through CLI/MCP output;
    - policy-unroutable recommendations;
    - realistic captured effective-pricing parsing.
  - Backfill parsing is tested primarily with synthetic dictionaries.
  - The MCP suite is live-only and does not deterministically assert the complete
    three-price payload.
- Required correction:
  - Add deterministic unit, fixture, mocked integration, and failure-path tests
    required by the Execution Contract.
  - Add a sanitized realistic effective-pricing fixture.
  - Ensure realistic supported payload-shape changes fail the offline suite.
  - Keep all real network access outside the default test gate.
- Required regression tests:
  - Each listed missing path.
  - End-to-end mocked retrieval → parse → normalize → store → output.
  - CLI JSON and MCP return-shape assertions.
- Cross-check against evidence, before adding new tests: several evidence
  items were already resolved as side effects of PE2-001/002/003/005 (this
  session's earlier work in the same pass) -- verified each still passes
  rather than assumed:
  - "missing/partial endpoint prices" -- PE2-002 (`tests/test_policy_pricing.py`,
    `tests/test_pricing.py`).
  - "policy lookup failure during discovery" / "policy-unknown output" --
    PE2-003 (`tests/test_discovery.py`, `tests/test_tracker.py`).
  - "policy-unroutable recommendations" -- PE2-001/PE2-003
    (`tests/test_tracker.py`).
  - "request timeout"/"connection failure"/"malformed JSON"/"incorrect
    response shape" for the endpoint-stats route specifically -- PE2-003
    (`tests/test_network_failure_paths.py`, at the time scoped to
    `fetch_endpoint_policy_pricing` only).
  - "end-to-end mocked retrieval → parse → normalize → store → output" --
    already covered by `tests/test_tracker.py::test_run_tracker_same_day_rerun_does_not_shift_d1`
    (PE2-001; uses `dry_run=False` and reads `history.csv` back from disk).
- Implementation evidence (remaining gaps closed by this finding):
  - `tests/test_network_failure_paths.py` extended: `fetch_openrouter_models()`
    (bulk catalog) and `fetch_effective_pricing_history()` (28-day backfill
    route) previously had NO direct failure-mode tests at all (only
    `fetch_endpoint_policy_pricing` did, from PE2-003) -- 12 new tests added,
    covering timeout/connection-error/HTTP-error/malformed-JSON/wrong-shape/
    success for both functions.
  - New sanitized fixture `tests/fixtures/openrouter_effective_pricing_gpt-5.6-luna_trimmed.json`
    (real, live-captured 2026-09-17, trimmed to 5 days) satisfies "Add a
    sanitized realistic effective-pricing fixture" and "realistic captured
    effective-pricing parsing" -- new test
    `test_reduce_to_daily_observations_parses_realistic_captured_fixture`
    parses it through the actual production reduction function.
  - `tests/test_mcp.py` was 100% `@pytest.mark.live` -- confirmed the exact
    evidence claim ("does not deterministically assert the complete
    three-price payload"). Two new deterministic (mocked, no network) tests
    added: `test_check_prices_zdr_preserves_three_price_distinction_deterministic`
    and `test_check_prices_zdr_unroutable_never_recommended_deterministic`,
    exercising `check_prices(zdr_only=True)` through the actual
    `server.call_tool` MCP boundary (not `run_tracker` directly), using
    isolated `tmp_path` + `ANTICHARON_CONFIG`/`ANTICHARON_DATA_DIR` env vars
    per this session's "do not depend on runtime `data/`" constraint.
  - `tests/test_cli.py` extended with two deterministic tests exercising
    `cmd_run` directly (not just `cmd_model`'s `discover` action, already
    covered): one asserts the printed `--json` payload's shape (effective/
    policy/routable fields), one asserts `POLICY_UNROUTABLE` actually
    renders in the human-readable output text (`capsys`), not just that the
    warning object exists on the `TrackerResult`.
  - `docs/plans/pricing-engine-v2/PLAN.md`'s Testing section updated to list
    the new fixture and test files.
- Remediation-agent verification:
  - `uv run pytest`: 139 passed, 3 deselected (was 122 before this finding;
    +17 new tests: 12 network-failure-path + 1 realistic-fixture + 2 MCP +
    2 CLI).
  - `uv run pytest -m live`: 3 passed, 139 deselected.
  - `uv run anticharon test`: PASS.
  - `git diff --check`: clean.
  - `ruff`: one genuine issue found and fixed (not merely disclosed): an
    actually-unused `import pytest` in the new `test_network_failure_paths.py`
    (F401, a real oversight, removed). Two additional findings disclosed as
    style-convention matches, not fixed: `C408` on `test_cli.py`'s new
    `_run_args()` helper's `dict(...)` call, which copies the exact same
    pattern as the pre-existing, unmodified `_discover_args()` helper
    immediately above it in the same file.
- Resolution commit: `a55b133`
- Independent retest:
  - Pending

### PE2-007 — CLI diagnostic verifies the retired two-component formula

- Severity: P2
- Status: `Ready for Retest`
- Contract impact:
  - Canonical pricing formula
  - Diagnostic trustworthiness
  - Legacy-path removal
- Affected files:
  - `src/anticharon/tester.py`
  - relevant diagnostic tests
- Evidence:
  - `anticharon test` reports “Mathematical Engine: Verified” after evaluating a
    two-component calculation equivalent to:

    ```python
    (1.0 * 0.99) + (2.0 * 0.01)
    ```

  - Cached-input/read pricing is not involved.
  - The diagnostic can pass if the canonical cached-token formula regresses.
- Required correction:
  - Verify the production three-component pricing function.
  - Use independently derived expected values.
  - Include a cache-heavy case that fails if cached pricing is omitted.
  - Keep the diagnostic fast and deterministic.
- Required regression tests:
  - Diagnostic passes with the canonical implementation.
  - Diagnostic fails or reports failure if cache-read pricing is ignored.
  - Zero-cache reference case remains correct.
- Implementation evidence:
  - `src/anticharon/tester.py`'s "Mathematical Formula Verification" step now
    calls the actual production `calculate_effective_cost`
    (`src/anticharon/pricing.py`) with two of the ADR's independently-derived
    golden cases (also used verbatim, unrounded, in `tests/test_golden_pricing.py`)
    as reference values: Golden Case #1 (cache-heavy, 85% cached, expected
    `$0.5174/1M`) and Golden Case #4 (zero-cache, expected `$2.3077/1M`).
    Neither number was re-derived here -- both are already independently
    verified in the golden-case test suite; this diagnostic reuses them
    rather than inventing new reference values.
  - The MA_3d/MA_7d portion of the same diagnostic step (unrelated to this
    finding's scope -- moving averages, not cached-token pricing) was left
    untouched; only the pricing-formula block was replaced.
  - New `tests/test_tester.py` (3 tests, deterministic -- OpenRouter
    connectivity mocked, isolated `tmp_path` via `ANTICHARON_CONFIG`/
    `ANTICHARON_DATA_DIR`):
    - "Diagnostic passes with the canonical implementation" --
      `test_run_self_test_math_engine_passes_with_canonical_implementation`.
    - "Zero-cache reference case remains correct" --
      `test_run_self_test_math_engine_zero_cache_reference_case_remains_correct`.
    - "Diagnostic fails or reports failure if cache-read pricing is ignored"
      -- `test_run_self_test_math_engine_fails_if_cache_read_pricing_ignored`:
      monkeypatches `calculate_effective_cost` with a legacy-2-component-
      equivalent implementation and confirms `run_self_test()` now genuinely
      returns `False` with a descriptive error -- proving the fix is
      load-bearing, since the original hardcoded check could never have
      caught this by construction (it called no production code at all).
- Remediation-agent verification:
  - `uv run pytest`: 142 passed, 3 deselected.
  - `uv run pytest -m live`: 3 passed, 142 deselected.
  - Manual: `uv run anticharon test` run directly against the live API,
    confirmed `[PASS] Mathematical Engine: Verified` with the new
    production-formula-backed check.
  - `git diff --check`: clean.
  - `ruff`: zero new findings (verified line-by-line against the diff hunks
    in `tester.py`; one genuinely unused `import pytest` in the new test
    file was found and removed, not merely disclosed).
- Resolution commit: `a3d5668`
- Independent retest:
  - Pending

### PE2-008 — `cache_hit_rate_used` contains a token weight, not a cache-hit rate

- Severity: P3
- Status: `Ready for Retest`
- Contract impact:
  - Output semantics
  - Calibration transparency
  - Data-model correctness
- Affected files:
  - `src/anticharon/tracker.py`
  - `src/anticharon/models.py`
  - related serialization tests
- Evidence:
  - `PricePoint.cache_hit_rate_used` is assigned `weight_cached_prompt`.
  - `weight_cached_prompt` is cached prompt tokens divided by all tokens.
  - Cache-hit rate is cached prompt tokens divided by prompt tokens.
  - For normalized weights:

    ```text
    cache_hit_rate =
      weight_cached_prompt
      ÷ (weight_uncached_prompt + weight_cached_prompt)
    ```

  - Live output showed approximately `0.764449`, while the configured default
    cache-hit assumption was approximately `0.766701`.
- Required correction:
  - Calculate the actual prompt cache-hit rate.
  - Define zero-prompt-weight behavior explicitly.
  - Keep naming and documentation consistent.
- Required regression tests:
  - Default weights.
  - Calibrated weights with nonzero completion share.
  - Zero cached weight.
  - Zero total prompt weight.
- Implementation evidence:
  - New `src/anticharon/pricing.py::derive_cache_hit_rate(weight_uncached_prompt,
    weight_cached_prompt)`: `weight_cached_prompt / (weight_uncached_prompt +
    weight_cached_prompt)`. Algebraically this is
    `(Cached/Total)/(Prompt/Total) = Cached/Prompt`, the correct cache-hit-rate
    definition -- not a fresh assumption, a derivation from the existing
    weight definitions (documented in the function's own docstring).
  - Zero-prompt-weight behavior explicitly defined (the "define the zero-
    prompt-weight behavior explicitly" required correction): both weights `0`
    (a degenerate 100%-completion mix) returns `0.0`, never a
    `ZeroDivisionError` and never a fabricated nonzero rate.
  - `src/anticharon/tracker.py`: both `PricePoint(cache_hit_rate_used=...)`
    call sites (the live-API path and the offline-cached-history fallback
    path) now use the derived rate instead of `w_cached` directly.
  - `src/anticharon/models.py`: `PricePoint.cache_hit_rate_used`'s inline
    comment corrected to state what it actually is.
  - **Strongest verification performed:** the default `weight_uncached_prompt`/
    `weight_cached_prompt` in `config.py` were themselves derived FROM an
    interim default cache-hit-rate of `0.766701` (`PLAN.md` "Core pricing
    semantics"). Deriving the rate back from those same weights round-trips
    to that exact original number (live-verified via `anticharon check
    --json`: reports `0.766701`, previously `0.764478`) -- this isn't merely
    internally consistent, it recovers the exact independently-known
    original value, the strongest possible confirmation the fix is correct.
  - Regression tests added: `tests/test_pricing.py` (4 unit tests, one per
    required-tests bullet -- default weights round-trip, calibrated weights
    with nonzero completion share, zero cached weight, zero total prompt
    weight) and `tests/test_tracker.py` (1 end-to-end test confirming the
    correct value flows through `run_tracker`'s `PricePoint`, not just the
    pure function in isolation).
- Remediation-agent verification:
  - `uv run pytest`: 147 passed, 3 deselected.
  - `uv run pytest -m live`: 3 passed, 147 deselected.
  - Manual: live-verified via `anticharon check --dry-run --json` against
    `openai/gpt-5.6-luna` with the default weights -- `cache_hit_rate_used`
    now reports `0.766701` (previously `0.764478`).
  - `git diff --check`: clean.
  - `ruff`: zero new findings (verified line-by-line against the diff hunks
    in all three touched files; `pricing.py`'s new function has zero
    findings on its own).
- Resolution commit: `b75dd1e`
- Independent retest:
  - Pending

### PE2-009 — Planning and validation documents are not synchronized

- Severity: P3
- Status: `Open`
- Contract impact:
  - Spec-driven development
  - Execution Contract authority
  - Release traceability
- Affected files:
  - `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`
  - `docs/plans/pricing-engine-v2/PLAN.md`
  - `docs/plans/pricing-engine-v2/ADR_CANDIDATE_TOKENS_CACHED.md`
  - `docs/specs/spec_v1_anticharon.md`
  - `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md`
- Evidence:
  - Duplicate Acceptance Criteria heading/section.
  - Duplicate Verification material.
  - Duplicate live-test bullet.
  - “No remaining open decisions” conflicts with refresh cadence marked `OPEN`.
  - The plan contains conflicting backward-compatibility statements.
  - The single-observation case contains
    `<explicit Anticharon-defined behavior>`.
  - Provider-granular persistence differs between contract/plan and the current
    specification/implementation.
  - The initially committed validation artifact omitted PE2-002 through PE2-010
    and contained only a template placeholder.
- Required correction:
  - Remove accidental duplication.
  - Resolve every remaining `OPEN` or explicitly retain it as a release blocker.
  - Resolve backward-compatibility policy consistently.
  - Define the single-observation dispersion behavior.
  - Reconcile provider-granular persistence through PE2-004.
  - Keep the Execution Contract, Plan, specification, ADR material, changelog,
    and validation ledger synchronized.
- Required verification:
  - Search for unresolved placeholders and contradictory normative statements.
  - Confirm all finding IDs remain present and stable.
  - Confirm repository-relative paths only.
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-010 — Quality-tooling policy is unclear and not enforced

- Severity: P3
- Status: `Open`
- Contract impact:
  - CI quality gates
  - Dependency hygiene
  - Release reproducibility
- Affected files:
  - `pyproject.toml`
  - `.github/workflows/ci.yml`
  - `AGENTS.md`
  - relevant changed source and test files
- Evidence:
  - `ruff check src tests` initially reported 245 findings.
  - CI runs pytest and the CLI diagnostic but not Ruff.
  - `pytest` and `ruff` are installed as runtime project dependencies.
  - The remediation agent reported 76 Ruff findings in files touched for
    PE2-001, all claimed to be pre-existing; this requires independent
    confirmation.
- Required decision:
  - Define the lint scope for this initiative.
  - Avoid an unrelated repository-wide style rewrite.
  - Ensure initiative changes do not introduce new lint violations.
  - Move test/lint tooling into an appropriate development dependency group if
    compatible with the supported packaging workflow.
  - Add a CI lint gate only when its scope is clean and explicitly documented.
  - Defer broader legacy cleanup explicitly if it remains out of scope.
- Required verification:
  - Ruff result for changed lines/files.
  - Dependency installation for end users excludes development-only tools where
    intended.
  - CI configuration matches documented gates.
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

## Acceptance-Criteria Traceability

| Requirement | Implementation | Test evidence | Status |
|---|---|---|---|
| Three-component cached-token formula | `src/anticharon/pricing.py` | Golden cases | Pass |
| Cache-heavy regression detection | Pricing and log parsing | Golden and real-log tests | Pass |
| Zero-cache behavior | Pricing logic | Golden case | Pass |
| Provider-aware effective pricing | Tracker endpoint resolution | Unit and fixture tests | Partial |
| Effective/policy distinction | PE2-001 remediation | Awaiting independent retest | Blocked |
| Policy-unroutable recommendations | PE2-001 remediation | Awaiting independent retest | Blocked |
| Policy-unknown graceful degradation | Tracker/discovery | Missing/inconsistent | Blocked |
| Missing/partial pricing fallback | Endpoint/catalog parser | Missing | Blocked |
| Provider-granular persistence | Not implemented as planned | None | Blocked |
| 28-day backfill | Tracker/storage | Partial synthetic and live coverage | Partial |
| Same-day rerun idempotency | Derived dated observations | Unit/integration tests | Pass |
| Public/internal listed-price canary | Live test | Does not test promised equality | Blocked |
| Realistic effective-pricing fixture | Not present | None | Blocked |
| Timeout/HTTP/malformed failure paths | Partial implementation | Incomplete | Blocked |
| CLI diagnostic canonical formula | Uses legacy two-component check | Inadequate | Blocked |
| Correct cache-hit-rate output | Incorrect value assigned | Missing | Blocked |
| Deterministic offline pytest gate | Pytest configuration and CI | Passed initially | Pass |
| Explicit live-test isolation | `@pytest.mark.live` | Passed initially | Pass |
| CI merge gate | GitHub Actions | Pytest and diagnostic configured | Partial |
| Contract/plan/spec synchronization | Documentation | Contradictions remain | Blocked |
| Version/changelog/tag consistency | Release files | Pending remediation/release | Blocked |

## Required Release Gates

- [ ] PE2-001 independently retested and resolved.
- [ ] All P1 findings resolved.
- [ ] All release-required P2 findings resolved.
- [ ] Any deferred finding explicitly approved and synchronized across the
      Execution Contract, Plan, specification, backlog, and validation ledger.
- [ ] Regression tests added for every behavioral defect.
- [ ] Realistic effective-pricing fixture added and parsed offline.
- [ ] Deterministic `uv run pytest` passes without network access.
- [ ] `uv run pytest -m live` passes separately.
- [ ] `uv run anticharon test` validates the canonical three-component formula.
- [ ] Manual normal-versus-ZDR output preserves advertised, effective, policy,
      and routability semantics.
- [ ] Policy-unroutable models are never recommended under the policy.
- [ ] Policy-unknown behavior matches the documented fallback rule.
- [ ] Same-day rerun remains idempotent.
- [ ] Agreed Ruff/static-analysis scope passes.
- [ ] `git diff --check` passes.
- [ ] CI passes on the integrated release commit.
- [ ] Feature branch is reconciled with the release branch.
- [ ] Version is selected according to SemVer and repository governance.
- [ ] `pyproject.toml`, `src/anticharon/__init__.py`, `README.md`, and
      `CHANGELOG.md` contain the same version.
- [ ] `[Unreleased]` is cut into the release section and restored empty.
- [ ] Final tests pass on the exact release commit.
- [ ] Release tag does not already exist.
- [ ] Release tag points to the independently validated release commit.
- [ ] No existing tag is moved, overwritten, or force-updated.

## Retest Log

### Remediation pass 1 — PE2-001

- Date: `2026-09-16`
- Implementation commit: `70fe99bf540ef8f233bc6db373797b299eb93547`
- Ledger commit: `c112b2c8ae95cbd3e979d2bc3b68d9e1683e4d03`
- Finding: PE2-001
- Remediation status: `Ready for Retest`
- Remediation-agent offline result: 89 passed, 3 deselected
- Remediation-agent live result: 3 passed, 89 deselected
- Remediation-agent diagnostic result: PASS
- Independent result: pending
- Release decision: `BLOCKED`

### Independent retest 1 — Pending

- Date:
- Tested commit:
- Disposable-checkout environment:
- Findings tested:
- Findings resolved:
- Findings reopened:
- Offline gate:
- Live gate:
- Diagnostic gate:
- Manual verification:
- Lint/static analysis:
- CI result:
- Release decision:

## Final Sign-Off

- Final validated feature commit:
- Integrated release-branch commit:
- Released version:
- Release commit:
- Release tag:
- Remote branch/tag verification:
- Decision: `BLOCKED`
- Reviewer:
- Date: