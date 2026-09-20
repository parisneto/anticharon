# Mandatory Execution Contract — Post-Launch Sprint 1

> This is the sole planning document for this sprint (no separate `PLAN.md` or ADR,
> by explicit scope decision — see "Document set" below). It MUST remain
> synchronized with the implementation as work proceeds; any material change to
> scope, acceptance criteria, non-goals, or testing strategy MUST update this
> document in the same change.

Written by: parisneto (human) + planning agent
Reviewed by: *pending*
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

Required end-state behavior (matches the issue's own "Expected behavior" section):

- The CLI-tier fallback parser understands the Hermes YAML list format
  (`- provider: openrouter\n  model: <slug>`) in addition to the existing JSON form.
- If fallback output is present (non-empty) but cannot be parsed into any model,
  CLI detection is treated as **incomplete**, not as a successful default-only
  result — `get_hermes_models()` must fall through to Tier 2 file parsing in that
  case, not just when Tier 1 returns `None`/falsy.
- The file-tier parser retains the final fallback item regardless of whether the
  YAML block ends at EOF or is closed by a subsequent top-level key.
- `sync_hermes_to_config()` must never overwrite an existing multi-model shortlist
  with a shorter/default-only list when the detection that produced it was
  incomplete. A resolution mechanism (e.g. an explicit `incomplete: bool` signal
  threaded from `fetch_models_from_cli()` / `extract_models_from_file()` through to
  the sync call) is required — the exact plumbing is an implementation decision,
  not fixed here, but the outcome ("never downgrade the shortlist off an
  incomplete read") is a hard acceptance criterion.
- A warning is surfaced to the user (CLI/stderr, and in `--json` output) when
  Hermes detection is incomplete.
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
- Must not touch or affect the 38 pre-existing behavioral findings already
  fingerprinted in `docs/standards/lint_baseline_pe2010.txt` (`BLE001`, `B023`,
  `S110`/`S112`, `PLW1510`) — those remain deferred per the existing human
  sign-off recorded in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#pe2-010`,
  since they require dedicated regression tests to confirm no behavior change.
  This sprint's autofix is a distinct, narrower action from that deferred item.
- No behavior change is expected or permitted from the autofix; the full `pytest`
  suite must pass identically before and after.

### Test suite

No new test infrastructure. Extend the existing targeted files:

- `tests/test_hermes.py` (currently covers inline-JSON and multiline-YAML fallback
  parsing, plus `run_tracker` Hermes integration) — add cases for: CLI-tier YAML
  fallback parsing; CLI-tier non-empty-but-unparseable fallback output falling
  through to file-tier; file-tier trailing-item retention when a top-level key
  follows the fallback block; `sync_hermes_to_config` refusing to shrink the
  shortlist on incomplete detection; `anticharon test` divergence warning.
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
- The 38 fingerprinted findings in `docs/standards/lint_baseline_pe2010.txt`
  remain present and untouched (same rule codes, same file:line fingerprints) —
  confirming the autofix did not reach into deferred-behavioral territory.
- No new lint findings are introduced.

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
