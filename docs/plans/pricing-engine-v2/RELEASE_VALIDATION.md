# Pricing Engine v2 — Release Validation

## Validation Target

- Branch: `pricing-engine-v2`
- Commit: `90aaa06`
- Version: `v0.5.2`
- Validation date: `2026-09-16`
- Reviewer: Codex Model : GPT 5.6 Sol Light, Sept, 16th 2026 14:28pm GMT-3
- Status: `BLOCKED`

## Scope

Cross-validation against:

- `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`
- `docs/plans/pricing-engine-v2/PLAN.md`
- `docs/plans/pricing-engine-v2/ADR_CANDIDATE_TOKENS_CACHED.md`

## Verification Results

| Gate | Result | Evidence |
|---|---|---|
| Offline pytest | PASS | 86 passed, 3 deselected |
| Live pytest | PASS | 3 passed, 86 deselected |
| CLI diagnostic | PASS | OpenRouter reachable |
| Manual ZDR check | FAIL | Semantic defects found |
| Ruff | FAIL | 245 findings |

## Findings

### PE2-001 — Effective and policy prices collapse under ZDR

- Severity: P1
- Status: Open
- Affected files:
  - `src/anticharon/tracker.py`
  - `src/anticharon/models.py`
- Contract impact:
  - Three-price distinction
  - Policy-constrained recommendations
  - Consistent downstream calculations
- Evidence:
  - Normal Luna effective price: `$0.03267`
  - ZDR output mislabeled policy price as effective: `$0.06534`
  - Unroutable Qwen model was recommended as `BEST_OPTION_CHANGED`
- Required correction:
  - Preserve effective and policy prices independently.
  - Do not recommend policy-unroutable models under an active policy.
  - Compare like-for-like current and historical prices.
- Regression tests required:
  - ...
- Resolution commit:
- Retest result:

<!-- Repeat PE2-002, PE2-003, etc. -->

## Acceptance-Criteria Traceability

| Requirement | Implementation | Tests | Status |
|---|---|---|---|
| Three-component pricing | `src/anticharon/pricing.py` | Golden cases | Pass |
| Effective/policy distinction | Tracker and serializers | Incomplete | Blocked |
| Missing/partial pricing fallback | Endpoint parser | Missing | Blocked |
| 28-day backfill | Tracker/storage | Partial | Blocked |
| Provider-granular persistence | Not implemented | None | Blocked |

## Required Release Gates

- [ ] All P1 findings resolved.
- [ ] All P2 findings resolved or explicitly deferred through an approved plan change.
- [ ] Execution Contract and plan synchronized.
- [ ] Regression tests added for every behavioral defect.
- [ ] `uv run pytest` passes offline.
- [ ] `uv run pytest -m live` passes.
- [ ] `uv run anticharon test` passes.
- [ ] Manual normal-versus-ZDR output validated.
- [ ] CI passes.
- [ ] Version files and changelog synchronized.
- [ ] Release tag created only after final validation.

## Retest Log

### Retest 1 — YYYY-MM-DD

- Commit:
- Version:
- Fixed findings:
- Remaining findings:
- Offline gate:
- Live gate:
- Manual verification:
- Release decision: `PASS` / `BLOCKED`

## Final Sign-Off

- Validated commit:
- Released version:
- Release tag:
- Decision:
- Reviewer:
- Date: