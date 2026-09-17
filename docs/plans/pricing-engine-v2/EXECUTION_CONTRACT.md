# Mandatory Execution Contract - TL/DR style of the PLAN.md

> This section is the authoritative short-form representation of the current plan.
> It MUST remain synchronized with the detailed plan, ADRs, evidence, implementation
> artifacts, and accepted decisions.
>
> Any material change to scope, architecture, acceptance criteria, non-goals, or
> testing strategy MUST update this section in the same change.

Written by: parisneto (human) + remediation coding agent
Reviewed by: Codex (independent release validation, `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md`)
Last synchronized: 2026-09-17
Plan/ADR revision: `PLAN.md` revision 3; `docs/specs/adr/0002_internal_frontend_stats_api_for_historical_trajectories.md` amendment 2026-09-17

## 1. Anticharon Feature Chosen for This Plan

Upgrade Anticharon's main pricing retrieval and calculation engine and its
downstream use throughout Anticharon's pricing, comparison, recommendation,
and output logic.

The feature includes:

- expanded provider-level pricing retrieval;
- listed versus actual/effective provider pricing where supported by evidence;
- cached-token pricing;
- provider/routing differences relevant to effective cost;
- local storage/schema changes required by the expanded pricing model;
- scraped 28-day detailed pricing history to provide historical backfill from
  the user's first day of Anticharon usage;
- propagation of the upgraded pricing model through compound-price calculations,
  comparisons, recommendations, and user-visible outputs.

## 2. Outcome Definition

Anticharon must represent and calculate model cost using the pricing dimensions
that materially affect a real agent workload rather than relying on the current
simplified gross input/output model.

The upgraded engine must correctly support, where data is available:

- input-token pricing;
- output/completion-token pricing;
- cached-input/read pricing;
- provider-specific pricing;
- listed versus actual/effective pricing semantics;
- historical pricing required for initial 28-day backfill.

The change must propagate consistently through Anticharon's storage,
calculations, comparisons, recommendations, and outputs.

### Representative / Golden Use Cases

Create a small set of explicit golden cases representing realistic Anticharon
usage patterns.

At minimum include:

1. Standard workload with no cached tokens.
2. Cache-heavy agent workload where cached-input pricing materially changes
   effective cost.
3. Same model routed through providers with materially different prices.
4. A case where provider/routing constraints materially alter the economically
   available price.
5. Missing/partial pricing data with the explicitly defined fallback behavior.
6. Historical/backfill case demonstrating correct use of retrieved history.

Golden cases MUST define inputs and expected outputs independently enough to
detect incorrect pricing formulas.

Representative cases and their meaning should be visible in the appropriate
project artifacts (tests/specification/documentation/README) without duplicating
unnecessary implementation detail.

### Mature Test Suite

Adopt `pytest` as the standard testing framework for this feature and future
behavioral testing.

The feature's test evidence must include:

- deterministic unit tests for pricing and transformation logic;
- realistic sanitized JSON fixtures representing relevant external API payloads;
- fixture-based parsing/normalization tests;
- mocked integration tests covering retrieval → parsing → normalization →
  storage → calculation/output boundaries as appropriate;
- golden/reference pricing cases with exact expected calculations;
- negative/failure-path tests, including relevant timeout, HTTP/API failure,
  malformed payload, missing-field and partial-data behavior;
- regression tests for corrected defects, including the cached-token omission;
- explicitly marked opt-in live tests where useful for validating the current
  external API contract;
- deterministic mandatory gates that run without network access;
- CI execution of the mandatory test gates.

The existing timeout-forcing test may remain only if it genuinely validates
timeout/fallback behavior. It MUST NOT serve as evidence that realistic
response parsing or normal operation works.

## 3. Acceptance Criteria

The feature is complete when:

### Pricing model
- Cached-token pricing is represented explicitly and no longer omitted from
  supported effective-cost calculations.
- Provider-level pricing can be represented without collapsing materially
  different provider prices into an incorrect single value.
- Uncached pricing scenarios remain correctly calculated under the new pricing model; the legacy two-way gross-price calculation is removed as an independent downstream pricing path.
- Pricing formulas have explicit, deterministic golden cases with exact
  expected results.

### Retrieval and history
- On first use, Anticharon can scrape and persist the available 28-day public pricing history required for initial backfill. Subsequent runs update history without corrupting or unnecessarily duplicating stored observations.
- Required expanded pricing data can be retrieved and normalized into the
  Anticharon internal model.
- Re-running retrieval/backfill does not corrupt or incorrectly duplicate
  previously stored history.

### Storage
- Local persistence stores both the newly required pricing dimensions and the 28-day historical observations needed by downstream calculations.
- Existing stored data is either backward-compatible or has an explicit, tested migration/fallback path. **Resolved 2026-09-17 (PE2-009):** no backward-compatibility shim was added for the `current_price_1m` → `effective_price_1m` rename (a deliberate K.I.S.S. decision, pre-launch/single-digit testers — see `PLAN.md`'s "Core pricing semantics"); the fallback path is that a stale old-format `history.csv` degrades gracefully to empty history (never crashes, never misparses old columns into the new schema's different positions) rather than being migrated. Now explicitly tested: `tests/test_storage.py::test_history_csv_old_pre_rename_format_degrades_gracefully`.

### Downstream behavior

- All identified Anticharon calculations that consume pricing use the upgraded
  pricing representation consistently.

- The legacy two-way gross-price calculation is deprecated and removed as an
  independent downstream pricing path; pricing calculations, comparisons,
  recommendations, and outputs consume the new canonical pricing model.

- User-visible pricing must preserve the semantic distinction between materially
  different concepts such as listed, provider-specific, and workload-effective
  cost. Presentation is determined by the feature design and MUST NOT be misleading.

- Incomplete 28-day history is an expected and valid condition, particularly for
  newly launched or newly served models in Openrouter, and MUST NOT by itself be treated as
  an error. Calculations use the valid observations available and degrade
  gracefully when history is limited.

- Historical profiles MUST reflect the evidence actually available.
  `🌱 NEWLY_TRACKED` is used when history is insufficient for a stronger
  deterministic classification. Fewer than 28 days MUST NOT automatically imply
  `NEWLY_TRACKED`: when available observations satisfy the defined criteria,
  profiles such as `🛡️ STABLE`, `⚡ VOLATILE`, or `🐌 CREEPING_INFLATION`
  may be assigned.

- Missing historical observations MUST NOT be fabricated, extrapolated, or
  silently filled solely to enable calculations or profile classification.

Sample Golden cases:
- Single historical observation (i.e. a model tracked for exactly one day,
  zero backfill available)
  Expected:
  - mean = observed value (the single observation, trivially — see
    `price_min_30d`/`price_max_30d` in `tests/test_analytics.py::test_single_observation_zero_dispersion_golden_case`)
  - dispersion = `0.0%` (`volatility_cv_pct`) — **resolved 2026-09-17 (PE2-009):**
    the coefficient of variation of a single data point is mathematically
    zero (there is no second point to vary against), not undefined and not
    a fabricated nonzero guess. Live-verified against the actual
    implementation (`calculate_model_analytics`) and locked in by the test
    referenced above.
  - profile = 🌱 NEWLY_TRACKED
  - no synthetic historical observations


### Verification

- The mandatory deterministic `pytest` suite passes without network access.
- Golden/reference cases validate critical pricing calculations, including
  cached-token pricing, against independently derived expected values.
- Realistic fixture-based and mocked integration tests validate the supported
  retrieval → parsing → normalization → storage → calculation paths.
- Defined failure and fallback cases pass.
- Regression coverage MUST detect removal or incorrect application of
  cached-token pricing.
- Representative external payload changes that break supported parsing MUST
  cause deterministic tests to fail.
- The default gate is `uv run pytest` and runs all deterministic tests while
  excluding `@pytest.mark.live`.
- A small `smoke` subset MAY be used as an explicit emergency local bypass,
  but does not replace the default gate; CI still requires the default gate
  before normal merge.
- `@pytest.mark.live` tests validate selected external contracts and run
  explicitly or on a scheduled basis. They do not gate normal commits or PRs.
- Local Git hooks provide fast developer feedback; CI is the authoritative
  merge gate because local hooks can be bypassed.


### Documentation
- Relevant specs/ADR/documentation describe the pricing semantics and important
  assumptions.
- README/user-facing documentation contains only information necessary for a
  user to understand the resulting capability.
- The TL/DR Execution Contract is synchronized with the final implementation.



## 4. Non-Goals

Scope is bounded by the acceptance criteria. Anything not required to meet them is out:

- **Minimal change**: no refactoring, rewriting, or optimizing code or tests the criteria don't touch.
- **Concrete over general**: support the in-scope cases only; no generalizing for hypothetical providers, pricing schemas, or analytics. Do not solve adjacent discoveries unless required by the defined outcome.
- **Tests serve the criteria**: Do not add infrastructure, abstractions, or testing sophistication without a demonstrated need for this feature.
- **No OpenRouter parity**: no dashboard replication, no fixing every pricing inconsistency, no history beyond the supported backfill.

- Preserve worthwhile discoveries in **Deferred**, rather than expanding the current scope.

## Deferred / Still Open for a Future Planning Round

Items discovered during implementation belong here unless explicitly approved and promoted into the current scope.

Current candidates:
- **Provider-granular historical persistence (PE2-004, deferred 2026-09-17):** `PLAN.md`'s original "Storage architecture" section described a per-model, *per-provider* daily time series (`date`, `provider`, effective price, listed price, cache-hit rate, token share). The shipped implementation stores one collapsed cheapest-price-per-day observation per model instead — see `PLAN.md`'s "Scope correction" note under that section for the full reconciliation and rationale (no current downstream consumer needs provider-level history; building it speculatively would violate this section's own "concrete over general" rule above). Revisit only if a real feature proposal (e.g. a "cheapest provider over time" view, or historical cache-hit-rate trending) needs it — scope it as its own initiative against that concrete need, not sight-unseen.
- **Documentation/reality drift: `smoke` test subset (discovered during PE2-010, 2026-09-17):** the "Verification" section above states "A small `smoke` subset MAY be used as an explicit emergency local bypass," but no `smoke` pytest marker, mark registration, or subset selection exists anywhere in this repository (`grep -rn "smoke"` across `pyproject.toml`, `tests/`, `.github/workflows/`, `AGENTS.md` returns nothing). This line pre-dates PE2-010 and is out of that finding's affected-files scope, so it was not changed here — flagged for a future planning round to either implement the described `smoke` marker or remove the aspirational claim.
- **Repository-wide Ruff cleanup (discovered during PE2-010, 2026-09-17):** `ruff check src tests` reports 251 pre-existing findings unrelated to any single tracked initiative. Out of scope for a targeted bug-fix pass per this document's own "concrete over general" / "minimal change" Non-Goals. See `AGENTS.md`'s lint scope policy (Rule 8) and `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#pe2-010` for the current CI-gate decision. Revisit as its own initiative if/when a blanket `ruff check` CI gate is wanted.
- **Provider-Granular Persistence:** Deferred from PE2-004 — Granular historical persistence does not match the plan. The granular data has no current use, therefore should not persist. When we pick this up, it will unlock advanced provider routing scenarios, for new features based on OpenRouter's API, here is a few aditional filters that could be used:
  - Price ceilings (`max_price`)
  - Performance sorting (`sort: "throughput"` / `:nitro`)
  - Privacy enforcement (`data_collection: "allow" | "deny"`, `enforce_distillable_text`)
  - Based on the OpenRouter.ai Docs and API References : https://openrouter.ai/docs/guides/routing/provider-selection, https://openrouter.ai/docs/api_reference/parameters, 
  https://openrouter.ai/docs/guides/features/service-tiers