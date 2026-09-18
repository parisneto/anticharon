# Lint Remediation Policy

Unless lint remediation is an explicit goal of the current plan:

1. Safe Ruff fixes may be applied automatically with `ruff check --fix`.
2. Unsafe fixes MUST NOT be applied automatically.
3. Remaining Ruff findings are out of scope and MUST NOT be individually
   investigated, fixed, or documented.
4. Remaining findings are recorded in `Deferred` using:
   - the output of `ruff check src tests --statistics`
   - the affected files, with finding count and rule codes
5. A finding introduced by the current work in a changed file still blocks
   the lint gate unless explicitly accepted by the human.
6. Human-approved manual fixes are allowed when narrowly scoped and verified
   by the relevant tests.

When lint remediation is itself an explicit goal of the plan, the plan defines the applicable scope, rules, tests, and acceptance criteria.

## Lint Gate

- Run safe fixes: `ruff check src tests --fix`
- Current-work files MUST introduce no unresolved Ruff findings unless
  explicitly accepted by the human.
- Pre-existing/out-of-scope findings do not block this release.
- Record remaining repository lint debt under `Deferred` as:
  1. `ruff check src tests --statistics`
  2. affected-file summary: file → count → rule codes ( suggested sample script for inventory : scripts/summarize_lint.sh)
