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
- Status: `Open`
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
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-003 — Policy lookup failure is treated as confirmed noncompliance

- Severity: P1
- Status: `Open`
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
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-004 — Granular historical persistence does not match the plan

- Severity: P2
- Status: `Open`
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
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-005 — Live backfill canary does not perform the promised cross-validation

- Severity: P2
- Status: `Open`
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
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-006 — Mandatory failure-path and realistic-payload coverage is incomplete

- Severity: P2
- Status: `Open`
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
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-007 — CLI diagnostic verifies the retired two-component formula

- Severity: P2
- Status: `Open`
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
- Resolution commit:
  - Pending
- Independent retest:
  - Pending

### PE2-008 — `cache_hit_rate_used` contains a token weight, not a cache-hit rate

- Severity: P3
- Status: `Open`
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
- Resolution commit:
  - Pending
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