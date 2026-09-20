# Mandatory Execution Contract — Post-Launch Sprint 1

> This is the sole planning document for this sprint (no separate `PLAN.md` or ADR,
> by explicit scope decision — see "Document set" below). It MUST remain
> synchronized with the implementation as work proceeds; any material change to
> scope, acceptance criteria, non-goals, or testing strategy MUST update this
> document in the same change.

Written by: parisneto (human) + planning agent
Reviewed by: independent review agent (2026-09-20 pass — Hermes detection-outcome
model, source-order/sync-protection rules, lint-baseline gate; see dated entries
in the relevant sections below)
Last synchronized: 2026-09-20
Tracking: [Issue #4](https://github.com/parisneto/anticharon/issues/4) (bug, critical),
[Issue #3](https://github.com/parisneto/anticharon/issues/3) (bug).
[Issue #5](https://github.com/parisneto/anticharon/issues/5) (bug, `uv.lock`
corruption) was found during scoping and already fixed on `main` — see the
note below, not part of this sprint's remaining work.

## Base commit note — uv.lock fix landed outside this sprint

[Issue #5](https://github.com/parisneto/anticharon/issues/5) (`uv.lock` had a
duplicate `dev-dependencies` table, breaking `uv sync --frozen` on every fresh
clone) was found while scoping this sprint but is unrelated to Issues #4/#3, so
it was fixed and merged directly to `main` ahead of this sprint rather than
folded into its scope — see commits `ec326aa` (fix) and `9afcf8a` (Rule 11
version bump to `0.5.4`). The `v0.5.4` tag itself is deliberately deferred to
be pushed when this sprint's own PR closes, not pushed standalone.

**Consequence for implementation:** anyone starting the code work for this
sprint (see the start prompt already circulated) must branch/worktree from the
current `main` tip (post-`9afcf8a`), not from the older commit `main` was at
when this contract was first drafted (`6bf0ad8`) — that older commit has the
broken lock file. Anyone with an existing local venv from before this fix
should reset it before continuing work here:

```bash
git pull origin main   # or re-branch/worktree from the current main tip
rm -rf .venv
uv sync
```

## Document set

Per pricing-engine-v2 precedent (`docs/plans/pricing-engine-v2/`), a full initiative
gets `EXECUTION_CONTRACT.md` + `PLAN.md` + ADR(s) + a running `RELEASE_VALIDATION.md`.
This sprint is scoped to two already-diagnosed bugs plus a bounded lint autofix pass,
so — by explicit human decision (2026-09-20) — it ships with **`EXECUTION_CONTRACT.md`
only**. No `PLAN.md`, no ADR, no separate `RELEASE_VALIDATION.md`. Any review findings
and sign-off get appended directly into this document's own sections as the work
proceeds.

## 1. Scope Chosen for This Sprint

Three items, confirmed by human decision on 2026-09-20:

1. **Fix Issue #4** — Hermes YAML fallback output is dropped and auto-sync overwrites
   the shortlist. (Critical: affects first-run ICP users on Hermes + OpenRouter.)
2. **Fix Issue #3** — `anticharon check --zdr` breaks the ASCII price-spectrum chart
   layout (overflowing bars, lost triangle shape).
3. **Safe lint autofix** — run `ruff`'s non-behavioral autofixes across the repository.

Everything else in `docs/BACKLOG.md`'s "Current Sprint" section (eval harness,
cache-hit-rate update, Pareto provider cutoff, `calibrate` MCP tool, universal
importers, model comparator, interactive picker) is explicitly deferred — not part
of this sprint. See "Non-Goals" and "Deferred" below.

## 2. Outcome Definition

### 2a. Issue #4 — Hermes CLI/file sync must never silently drop models

Root cause, confirmed by direct code inspection matching the issue's own analysis:

- `fetch_models_from_cli()` (`src/anticharon/hermes.py:61-129`) parses
  `hermes config get fallback_providers` output as JSON only (with a regex fallback
  that also only targets JSON object syntax). The current Hermes CLI emits a raw
  YAML list instead. Parsing silently yields `fallback_models = []`, and the function
  still returns a "successful" CLI result of `{default_model}` only — it never
  signals that fallback detection failed.
- `get_hermes_models()` (`hermes.py:242-264`) treats any truthy CLI result as
  final and never falls through to Tier 2 (`extract_models_from_file()`) once Tier 1
  "succeeds," even though that success was actually a partial/incomplete detection.
- `extract_models_from_file()` (`hermes.py:132-239`) has its own independent defect:
  when the `fallback_providers:` YAML block is closed by a following top-level key
  (indent 0) rather than by end-of-file, `in_fallback_block` is reset to `False`
  (line ~205) without first flushing the in-progress `current_fallback_provider` /
  `current_fallback_model` pair — the last fallback entry is silently dropped. (The
  EOF case at line ~224 already flushes correctly; only the "another section
  follows" case is broken.)
- `sync_hermes_to_config()` (`hermes.py:267-289`) persists whatever `all_models`
  list it is handed with no completeness check, so a partial detection result
  overwrites a previously-good multi-model shortlist on disk.

**Reviewed decision (2026-09-20 — independent review): formal detection-outcome
model.** The fix is defined in terms of three named outcomes per source (CLI
tier, file tier), not a binary success/failure:

- **`complete`**: the source provides a parseable default model AND the
  complete configured fallback-model set.
- **`incomplete`**: the source demonstrates that a model configuration
  exists, but Anticharon cannot establish the complete model set. The known
  example is non-empty CLI `fallback_providers` output from which no
  fallback model can be parsed.
- **`unavailable`**: the source cannot be read or queried at all — missing
  executable/file, timeout, non-zero command exit, or an equivalent access
  failure.
- No in-process retry loop is added in this sprint for an `unavailable`
  source. A later invocation (the next scheduled/manual run) may retry it.

**Source order is preserved, not reversed:**

- The Hermes CLI is preferred when it returns a `complete` result, since it
  represents the actively resolved configuration (not a static file that may
  be stale relative to environment overrides).
- If CLI detection is `incomplete` or `unavailable`, the file tier is tried.
- A `complete` file-tier result is the authoritative final result: it clears
  the `incomplete` CLI state entirely and must NOT emit an incomplete-detection
  warning — this is a full recovery, not a degraded fallback.
- This file-based recovery pattern may be reusable by a future one-way
  importer (e.g. a prospective OpenClaw or other orchestrator integration —
  see `docs/BACKLOG.md`'s "Universal One-Way Shortlist Importers"), but
  generalizing it for other integrations is explicitly out of scope for this
  sprint.

Required end-state behavior (matches the issue's own "Expected behavior"
section, refined against the outcome model above):

- The CLI-tier fallback parser understands the Hermes YAML list format
  (`- provider: openrouter\n  model: <slug>`) in addition to the existing JSON form.
- Non-empty, unparseable CLI fallback output is an `incomplete` CLI result —
  `get_hermes_models()` must try the file tier in that case, not just when the
  CLI call itself is `unavailable` (no executable, timeout, non-zero exit).
- The file-tier parser retains the final fallback item regardless of whether the
  YAML block ends at EOF or is closed by a subsequent top-level key.
- **Sync protection applies to the final selected result, not per-tier:**
  - If the final selected result (after trying CLI then file) is `complete`,
    it is authoritative and may legitimately shrink the shortlist — a genuine
    reduction in Hermes's configured models must propagate.
  - If the final selected result is `incomplete`, `sync_hermes_to_config()`
    must never overwrite an existing valid multi-model shortlist with a
    shorter/default-only list derived from it.
  - If CLI is `incomplete`/`unavailable` AND the file tier also fails to
    produce a `complete` result (i.e. the file tier is itself `incomplete` or
    `unavailable`), the existing shortlist is preserved unchanged and a
    visible warning is emitted in both human CLI output and `--json`.
  - If both CLI and file are `unavailable` (no Hermes present at all, or
    genuinely unreachable), existing configuration/standalone behavior is
    preserved — this is the ordinary no-Hermes case, not a new warning path.
  - A `complete` file-tier recovery from an `incomplete` CLI result clears
    that incomplete state entirely: the file result is used, sync is
    permitted, and no incomplete-detection warning is emitted (see "Source
    order is preserved" above).
  - The exact plumbing for carrying outcome state from `fetch_models_from_cli()`
    / `extract_models_from_file()` through to the sync call is an
    implementation decision, not fixed here — the outcomes above are the hard
    acceptance criteria.
- `anticharon test` flags a divergence between the currently detected Hermes model
  set and the persisted Anticharon shortlist, rather than reporting an unqualified
  pass.

**Explicitly out of scope for this fix** (see Non-Goals/Deferred): the issue's
"Related path-resolution observation" about `XDG_CONFIG_HOME`/`XDG_DATA_HOME`
first-run directory selection in `src/anticharon/config.py`. The reporter
themselves confirms it "does not cause the destructive sync." Deferred to a future
round rather than folded into this bug fix.

### 2b. Issue #3 — `--zdr` chart must render a correct, monotonic spectrum

Root cause, confirmed by direct code inspection matching the issue's own analysis:

- `tracker.py:590` sorts `prices_shortlist` by `_rank_price_1m()`, which ranks by
  the ZDR **policy** price when `--zdr` is active (unroutable models pushed to
  `math.inf`) — correct and intentional for recommendation ranking.
- `cli.py:96` passes that same ZDR-ranked list directly into
  `render_ascii_price_bar()` (`chart.py`), which assumes the input is sorted by
  **effective** `price_1m` and derives its 100%-width scale from
  `prices[-1].price_1m` (`chart.py:30`) — under `--zdr` this is whatever model
  ranked last by policy price, which can have an arbitrarily low *effective*
  price, blowing up every other bar's ratio far past 100%.

Required end-state behavior:

- `render_ascii_price_bar()` must produce a correct, monotonically-scaled chart
  regardless of the sort order of the list it is given. Resolution approach: the
  chart function computes its display scale from `max(p.price_1m for p in prices)`
  (not the last element) and renders against a defensively-sorted-by-`price_1m`
  local working copy, so the visual triangle shape and bar proportions are always
  correct — without changing `tracker.py`'s ZDR recommendation-ranking order used
  elsewhere (main list display, `BEST_OPTION_CHANGED`), which is intentional and
  out of scope to alter.
- Regression test: feed `render_ascii_price_bar()` a list in ZDR-policy order
  (cheapest-by-effective-price not first, an unroutable/`math.inf`-ranked model
  present) and assert the rendered bars are monotonically non-decreasing in width
  and the scale/`🏆 [BEST]` badge reflect true cheapest effective price.

### 2c. Safe lint autofix

- Run `ruff check --fix` (safe, non-behavioral fixes only — no `--unsafe-fixes`)
  across `src/` and `tests/`.
- **Reviewed correction (2026-09-20 — independent review):** the 38
  pre-existing behavioral findings fingerprinted in
  `docs/standards/lint_baseline_pe2010.txt` (`BLE001`, `B023`, `S110`/`S112`,
  `PLW1510`) must remain the same *semantic* findings — same rule code, same
  underlying code construct — but a safe autofix elsewhere in a file can
  legitimately shift their line numbers (e.g. removing a blank line or an
  unused import above them). The baseline's exact `<rule> <file>:<line>`
  fingerprints are therefore NOT required to stay byte-for-byte identical;
  what is required is that every one of the 38 findings still maps to the
  same pre-existing issue, and that no new (39th) finding is hidden behind a
  shifted/regenerated baseline.
- If the autofix does shift any of the 38 findings' line numbers, the
  fingerprint baseline may only be regenerated after an **independent
  cross-review agent** verifies, finding-by-finding, that each of the 38
  entries in the new baseline maps to the same pre-existing finding as before
  (not a coincidentally similar new one) and that the count is still exactly
  38. That sign-off is recorded in this contract (see "Independent
  Cross-Review Sign-Off Log" below and Acceptance Criteria → Lint autofix)
  before the release is cut — it is a strict release gate, not an optional
  review.
- These 38 findings remain deferred per the existing human sign-off in
  `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#pe2-010` — dedicated
  regression tests are still required before any of them can be fixed, which
  stays out of scope for this sprint regardless of line-number drift.
- No behavior change is expected or permitted from the autofix; the full `pytest`
  suite must pass identically before and after.

### Test suite

No new test infrastructure. Extend the existing targeted files:

- `tests/test_hermes.py` (currently covers inline-JSON and multiline-YAML fallback
  parsing, plus `run_tracker` Hermes integration) — add cases for: CLI-tier YAML
  fallback parsing; file-tier trailing-item retention when a top-level key
  follows the fallback block; `anticharon test` divergence warning; and one
  deterministic test per detection-outcome combination in the matrix under
  Acceptance Criteria → Hermes sync below (complete CLI; incomplete CLI +
  complete file; unavailable CLI + complete file; incomplete CLI +
  incomplete/unavailable file; unavailable CLI + unavailable file) — each
  asserting both which result is selected/used AND whether a
  warning/shortlist-preservation path fires, per the reviewed sync-protection
  rules above.
- `tests/test_chart.py` (currently one rendering-sections test) — add a case with
  a ZDR-policy-ordered input list asserting monotonic bar widths and correct scale.
- No fixture/mocking infrastructure changes needed; existing `tmp_path` /
  `monkeypatch` patterns in `tests/test_hermes.py` are sufficient.

## 3. Acceptance Criteria

The sprint is complete when:

### Hermes sync (Issue #4)
- CLI-tier fallback parsing supports the raw YAML list format Hermes v0.21.3
  emits, alongside the existing JSON format.
- Non-empty, unparseable CLI fallback output causes detection to be treated as
  incomplete and triggers fallback to file-tier parsing — it never returns a
  "successful" default-only result.
- File-tier parsing retains the last fallback item when the YAML block is closed
  by a following top-level section, not only at EOF.
- `sync_hermes_to_config()` never persists a shortlist shorter than/derived from
  an incomplete detection over an existing valid multi-model shortlist.
- A visible warning is surfaced when Hermes detection is incomplete.
- `anticharon test` reports a divergence between detected Hermes models and the
  persisted shortlist instead of an unqualified pass.
- **Detection-outcome combination matrix (reviewed decision, 2026-09-20) —
  each combination has a defined, tested behavior; the CLI → file tier order
  is never reversed:**
  1. Complete CLI result → use CLI.
  2. Incomplete CLI + complete file result → use file, permit sync (the file
     result may shrink the shortlist), no incomplete-detection warning.
  3. Unavailable CLI + complete file result → use file, permit sync, no
     incomplete-detection warning.
  4. Incomplete CLI + incomplete/unavailable file result → preserve the
     existing shortlist unchanged and emit a visible warning (CLI + `--json`).
  5. Unavailable CLI + unavailable file result → preserve existing
     configuration/standalone behavior (the ordinary no-Hermes case).
- All six "Suggested regression coverage" cases from Issue #4 are covered by
  tests: YAML multiline fallback; JSON fallback (existing, keep passing);
  unparseable-but-non-empty fallback; trailing-item-retention with a following
  top-level section; sync preserving shortlist on incomplete detection; self-test
  divergence warning.

### `--zdr` chart (Issue #3)
- `anticharon check --zdr` renders bars that are monotonically proportional to
  each model's effective `price_1m`, regardless of the list's ZDR-ranked input
  order.
- The chart's scale (100%-width reference) is always the true maximum effective
  price among the rendered models.
- `🏆 [BEST]` badges the model with the lowest effective price, matching the
  displayed triangle shape.
- `tracker.py`'s ZDR-policy ranking behavior for the main list and
  `BEST_OPTION_CHANGED` recommendation is unchanged by this fix.

### Lint autofix
- `ruff check --fix` applied repository-wide produces zero behavioral change:
  full `pytest` suite passes identically before and after.
- **Reviewed correction (2026-09-20):** the 38 findings fingerprinted in
  `docs/standards/lint_baseline_pe2010.txt` remain the same 38 *semantic*
  findings (same rule code, same underlying construct) — their exact line
  numbers may shift as a side effect of the safe autofix elsewhere in the
  same file; this is permitted, and a byte-for-byte fingerprint match is
  NOT required.
- No new lint findings are introduced, and no pre-existing finding is
  concealed by a coincidental fingerprint collision after any line shift.
- **Release gate:** if any of the 38 findings' line numbers shifted, the
  regenerated baseline is only valid once an independent cross-review agent
  has signed off — verifying every entry maps 1:1 to the same pre-existing
  finding and that the count is still exactly 38. That sign-off (reviewer,
  date, and the finding-by-finding mapping outcome) MUST be recorded in the
  "Independent Cross-Review Sign-Off Log" section below before the release
  is cut. No line-number drift → no cross-review needed; the sign-off
  requirement applies only when drift actually occurs.

### Verification
- The mandatory deterministic `pytest` suite (`uv run pytest`) passes without
  network access, including all tests added by this sprint.
- Regression tests exist and pass for every defect described in Issues #4 and #3.
- `ruff check` after autofix shows no unexpected diff against the pre-existing
  baseline beyond the intended autofix.

### Documentation & release governance
- `docs/BACKLOG.md`: remove/complete the items this sprint resolves; nothing else
  in it is touched.
- `CHANGELOG.md` updated under `[Unreleased]` per Rule 6, then rolled into a new
  version entry per the Rule 11 checklist.
- Per Rule 11 (Autonomous SemVer), this sprint is a **PATCH** release (bug fixes
  only, no CLI/schema changes) — expected `0.5.3` → `0.5.4`, executed as the
  final step of implementation, not during planning.
- This `EXECUTION_CONTRACT.md` stays synchronized with whatever is actually
  shipped; any resolved ambiguity (e.g. the exact "incomplete detection" signal
  mechanism) gets recorded here once implemented.

## 4. Non-Goals

Scope is bounded by the acceptance criteria above. Anything not required to meet
them is out:

- **Minimal change**: no refactoring of `hermes.py`/`chart.py`/`tracker.py` beyond
  what each defect requires. No behavioral rewrite of the Hermes import tiering
  strategy or the ZDR ranking algorithm.
- **No XDG path-resolution redesign**: the config/data directory first-run
  inconsistency noted in Issue #4 is explicitly deferred (see below) — it is not
  the destructive defect and reporter-confirmed as non-causal.
- **No behavioral lint fixes**: the 38 findings needing dedicated regression tests
  (`BLE001`, `B023`, `S110`/`S112`, `PLW1510`) stay out of scope; only safe,
  non-behavioral `ruff --fix` autofixes are in scope.
- **No other backlog items**: eval harness, cache-hit-rate update, Pareto cutoff,
  `calibrate` MCP tool, universal importers, model comparator, interactive
  picker — all remain in `docs/BACKLOG.md`, untouched by this sprint.
- **No test infrastructure changes**: existing `pytest`/`tmp_path`/`monkeypatch`
  patterns are reused as-is.
- **No in-process retry loop** for an `unavailable` Hermes detection source
  (a later invocation may retry it), and **no generalization** of the
  file-based recovery pattern for other prospective integrations (e.g. a
  future OpenClaw importer) — reviewed decision, 2026-09-20.

## Independent Cross-Review Sign-Off Log

Required only if the lint autofix pass (§2c / Acceptance Criteria → Lint
autofix) shifts the line number of any of the 38 pre-existing fingerprinted
findings in `docs/standards/lint_baseline_pe2010.txt`. Until that happens,
this log stays empty — no cross-review is owed for a no-drift autofix.

- *(none yet — populate with reviewer identity, date, and the
  finding-by-finding 38-of-38 mapping outcome once/if the fingerprint
  baseline is regenerated during implementation)*

## Deferred / Still Open for a Future Planning Round

- **XDG config/data path-resolution inconsistency (Issue #4's "Related
  path-resolution observation"):** `src/anticharon/config.py`'s `get_data_dir()`
  only selects `~/.local/share/anticharon/` when it already exists, otherwise
  falling back to the legacy `~/.anticharon/` even when `XDG_DATA_HOME` is
  documented as supported — while `get_config_path()` has a similar
  exists-first XDG check. Confirmed non-destructive by the reporter. Revisit as
  its own small fix once scoped, and add to `docs/BACKLOG.md` if not already
  captured.
- **Negative-token-count validation hardening (PE2-006)** — already tracked in
  `docs/BACKLOG.md`; explicitly not pulled into this sprint.
- **Repository-wide behavioral Ruff cleanup (38 fingerprinted findings)** —
  already tracked in `docs/BACKLOG.md` and `docs/standards/lint_baseline_pe2010.txt`;
  explicitly not pulled into this sprint (only the safe-autofix subset is).
- **All other `docs/BACKLOG.md` "Current Sprint" items** (eval harness,
  cache-hit-rate update, Pareto cutoff, `calibrate` MCP tool, universal
  importers, model comparator, interactive picker) — untouched, remain queued.
