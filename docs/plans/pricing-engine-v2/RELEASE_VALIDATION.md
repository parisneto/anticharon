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
- Status: Ready for Retest
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

---

**Implementation evidence (2026-09-16, this session — appended, original finding/evidence above left unmodified):**

- **Root cause:** `run_tracker` (`src/anticharon/tracker.py`) computed a single
  `display_price_1m` local that silently switched between the unconstrained
  effective price and the ZDR policy-constrained price depending on
  `zdr_only`, then reused that one collapsed value for `ModelPrice.price_1m`
  (the field serialized as `"effective_price_1m"` in CLI `--json` /
  `check_prices` MCP output), the shortlist sort key, `delta_7d_pct`/MA
  comparisons, and the `BEST_OPTION_CHANGED` recommendation. This directly
  violated `ModelPrice`'s own documented contract ("`price_1m` is the
  effective price... throughout the codebase," `src/anticharon/models.py`)
  and produced all three evidence items above:
  1. The JSON `effective_price_1m` field reported the policy price under
     `--zdr` (mislabeling).
  2. `delta_7d_pct`/`PRICE_SPIKE`/`PRICE_DROP` compared today's policy price
     against `ma_7d`/`ma_3d`, which are always derived from unconstrained
     effective historical observations in `effective_prices.json` (which
     never stores policy-price history) — an apples-to-oranges comparison.
  3. A model with no ZDR-compliant endpoint at all still fell back to its
     unconstrained effective price for sort/recommendation ranking, letting
     a fully policy-unroutable model be recommended via
     `BEST_OPTION_CHANGED`.
- **Files changed:**
  - `src/anticharon/tracker.py` — removed `display_price_1m`; `price_1m` and
    all its downstream consumers (MA fallback, `delta_7d_pct`, spike/drop
    messages) now always use `effective_price_1m`. Added a separate
    `_rank_price_1m` helper used only by the final sort and
    `BEST_OPTION_CHANGED` check: ranks by `policy_price_1m` when a policy
    filter is active, `math.inf` (never "cheapest", never recommended) for a
    model with no policy-compliant endpoint. `history.csv` persistence
    (`updated_records`) was already correctly using `effective_price_1m`
    throughout — this bug was confined to in-memory display/warning/sort
    logic, not persisted data (no data corruption to remediate).
  - `src/anticharon/models.py` — `ModelPrice.to_dict()` now defensively
    serializes `effective_price_1m` from `self.price.effective_price_1m`
    (the `PricePoint` ground truth) when present, rather than trusting
    `price_1m` blindly; defense-in-depth against the same class of bug
    recurring at the serialization boundary. Docstring updated to state the
    always-effective contract explicitly.
- **Tests added or changed** (`tests/test_tracker.py`):
  - Fixed `test_run_tracker_zdr_only_routable_uses_policy_price`: its
    `price_1m == policy_price_1m` assertion encoded this exact bug as
    expected behavior. Disclosed per `AGENTS.md` Rule 8 — corrected, not
    weakened; it now asserts `price_1m == effective_price_1m`, the behavior
    the class's own docstring always promised.
  - Added `test_run_tracker_zdr_effective_price_field_not_collapsed_with_policy`
    (evidence item 1), `test_run_tracker_zdr_never_recommends_unroutable_model_as_best_option`
    (evidence item 3), `test_run_tracker_zdr_delta_compares_effective_not_policy_price`
    (evidence item 2) — each hand-verified against the pre-fix formula to
    fail on the prior implementation before being added.
- **Implementation commit:** `70fe99b`
- **Specification/design decisions:** `docs/specs/spec_v1_anticharon.md` §3.1
  (new bullet: `effective_price_1m` never replaced by the policy price, in
  any surface) and §3.7 rule 3 (`BEST_OPTION_CHANGED` now explicitly
  excludes policy-unroutable models from "cheapest" ranking). No conflict
  found between `EXECUTION_CONTRACT.md`/`PLAN.md` and this fix — the
  Contract's "Policy-constrained recommendations" / "three-price
  distinction" requirements already mandated this behavior; the
  implementation had simply drifted from it. No ADR or Contract text
  required reconciliation.
- **Verification performed:**
  - `uv run pytest`: 89 passed, 3 deselected (offline, deterministic).
  - `uv run pytest -m live`: 3 passed.
  - `uv run anticharon test`: all diagnostics PASS.
  - Manual: reproduced the exact evidence scenario live against
    `openai/gpt-5.6-luna` + `qwen/qwen3.7-flash` (isolated temp data dir, not
    the repo's runtime `data/`). Confirmed Luna's `effective_price_1m` is
    identical (`$0.03265`) with and without `--zdr` (previously would have
    shown the ZDR policy price, `$0.065294`, under `--zdr`); confirmed no
    `BEST_OPTION_CHANGED` fires recommending the ZDR-unroutable Qwen model
    (`is_policy_routable: false`, correctly flagged `POLICY_UNROUTABLE`)
    even though its unconstrained effective price is cheaper than Luna's.
  - `git diff --check`: clean.
  - `ruff`: zero new findings introduced by this change (verified line-by-
    line against the diff hunks); all findings ruff reports on the touched
    files are pre-existing `UP006`/`UP045` style findings on lines this
    change did not modify, part of the 245 pre-existing repo-wide findings
    noted above, out of scope per `EXECUTION_CONTRACT.md`'s minimal-change
    Non-Goal.
- **Remaining risks / notes for independent reviewer:**
  - The offline-fallback path (`run_tracker` when the live API is
    unreachable and cached `history.csv` is used instead) does not compute
    or consider `zdr_only` at all — it never fetches live per-endpoint data,
    so policy-routability is fundamentally undeterminable offline. This
    path already never contained the `BEST_OPTION_CHANGED` logic block (it
    returns before reaching it), so it was never exposed to this defect;
    left untouched as out of scope for this fix.
  - Sibling-alternative discovery in `analytics.py` (used for
    `PROMO_ENDED`/`SUNSETTING` classification) consumes `price_1m` for
    candidate comparison; it now consistently receives the effective price
    in both `--zdr` and normal modes (previously inconsistent), which is a
    side-effect improvement of this fix but was not independently
    evidenced/required by PE2-001 and has no dedicated new test beyond the
    existing `test_analytics.py` coverage (unchanged, still passing).
  - This finding is left at `Ready for Retest`, not `Resolved` — final
    resolution is reserved for independent review per this document's
    release-governance process.
- **Retest result:** *(pending independent reviewer)*

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