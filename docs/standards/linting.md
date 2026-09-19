# Lint Remediation Policy

Unless lint remediation is an explicit goal of the current plan:

1. Safe Ruff fixes may be applied automatically with `ruff check --fix`.
2. Unsafe fixes, and any fix touching a behavioral rule (a rule whose fix can
   change runtime behavior, not just formatting/imports/typing annotations),
   MUST NOT be applied automatically. Behavioral autofixes require the same
   narrowly-scoped human approval as a manual fix (point 6 below).
3. Remaining Ruff findings are out of scope and MUST NOT be individually
   investigated, fixed, or documented.
4. Remaining findings are recorded in `Deferred` using:
   - the output of `ruff check src tests --statistics`
   - the affected files, with finding count and rule codes
5. A finding introduced by the current work on a changed line still blocks the
   lint gate unless explicitly accepted by the human (point 6).
6. Human-approved manual fixes are allowed when narrowly scoped and verified
   by the relevant tests. When a human explicitly approves deferring specific
   pre-existing findings instead of fixing them, the approval MUST be recorded
   as an **exact-fingerprint baseline** (`<rule> <file>:<line>` per finding),
   never as a blanket exemption by rule code alone. A blanket rule-code
   exemption would silently pass a brand-new, unrelated finding of the same
   code anywhere in the codebase; a fingerprint baseline cannot.

When lint remediation is itself an explicit goal of the plan, the plan defines the applicable scope, rules, tests, and acceptance criteria.

## Lint Gate

- Run safe fixes: `ruff check src tests --fix`.
- Current-work files MUST introduce no unresolved Ruff findings on lines that
  work modified or added, unless explicitly accepted by the human as an
  exact-fingerprint baseline entry (see point 6 above).
- Pre-existing findings on lines the current work did not touch are out of
  scope and MUST NOT block this release.
- Record remaining repository lint debt under `Deferred` as:
  1. `ruff check src tests --statistics`
  2. affected-file summary: file → count → rule codes (suggested sample
     script for inventory: `scripts/summarize_lint.sh`)

### Deterministic changed-line/baseline gate

`scripts/lint_gate.py [base_ref]` (default `base_ref`: `main`) enforces this
policy mechanically:

1. Computes the set of lines added/modified between `base_ref` and `HEAD` in
   `src/` and `tests/`.
2. Runs `ruff check src tests --output-format=json`.
3. A finding fails the gate only if **both** (a) its line falls inside that
   changed-line set, and **(b)** its exact `<rule> <file>:<line>` fingerprint
   is not present in an approved-baseline file
   (e.g. `docs/standards/lint_baseline_pe2010.txt` for the pricing-engine-v2
   initiative's PE2-010 approval).
4. Findings on untouched lines never fail the gate, regardless of rule code
   (pre-existing/out-of-scope legacy debt, point 3 above).
5. Findings on touched lines whose fingerprint is not baselined always fail
   the gate, including a new finding of an already-baselined rule code at a
   different location — this is what makes the exemption per-location rather
   than per-rule-code.

Each initiative that gets an explicit human-approved deferral creates its own
baseline file under `docs/standards/lint_baseline_<initiative>.txt` and passes
it via `scripts/lint_gate.py`'s baseline lookup; the current one in use is
`docs/standards/lint_baseline_pe2010.txt` (pricing-engine-v2's 38
human-approved `BLE001`/`B023`/`S110`/`S112`/`PLW1510` findings — see
`docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#pe2-010`).

`base_ref` defaults to `main` for ordinary future PR usage (a small diff
against the merge base). For verifying one remediation pass within an
already-long-lived feature branch (this branch is 38+ commits ahead of `main`
and predates the gate itself), pass the immediately-preceding evaluated
commit instead of `main` — diffing the whole branch against `main` would
re-surface every prior pass's already-reviewed lines as "changed," which is
not what this gate is for.

### CI status (documented, not aspirational)

`.github/workflows/ci.yml` currently runs `uv run pytest` and
`uv run anticharon test` only. It does **not** run `scripts/lint_gate.py` or a
blanket `ruff check` step. This is a deliberate, documented decision (not a
gap): `main` does not yet contain the pricing-engine-v2 initiative, so a
gate diffing against `main` today would conflate the entire initiative's
accumulated history with a genuinely new regression. Once this branch merges,
future PRs' diffs against `main` become small and the gate becomes accurate
for CI use — add the `scripts/lint_gate.py` step to CI at that point, scoped
to whichever baseline file(s) are then in force.
