# Effective History & Model Identity Sprint

## 1. Outcome

Correct history maturity, model identity, Hermes persistence, discovery,
MCP, and CLI ergonomics. [PLAN.md](PLAN.md) owns sequencing/evidence methods;
the [spec](../../specs/spec_v1_anticharon.md) owns detailed behavior.

Protocol baseline: MCP specification [2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28).

## 2. Acceptance Criteria

- **AC-1 — EH-1 / [#26](https://github.com/parisneto/anticharon/issues/26): Effective history maturity.**
  Use valid effective-price observation dates and covered history, rather
  than installation time alone. Sufficient day-0 backfill permits a normal
  first-run profile; new or insufficiently observed models remain
  `NEWLY_TRACKED`. Gaps stay null, with no synthetic observations. Document
  the exact coverage/configuration rule; expose observation count,
  earliest/latest dates, coverage span, and classification reason.
- **AC-2 — EH-2 / [#25](https://github.com/parisneto/anticharon/issues/25): Hermes persistence.**
  Complete sync persists explicit source/order/default metadata even when
  the sequence is unchanged. Hermes-owned entries may refresh each run;
  preserve manual models and user-enforced manual defaults, subject to the
  explicit precedence clarification in D-3. Repeated runs are idempotent
  without false `HERMES_DIVERGENT` or `NO_DEFAULT` messages.
- **AC-3 — EH-3 / [#27](https://github.com/parisneto/anticharon/issues/27): First-class analytics.**
  `run` and `history` classify identical stored evidence identically.
  Human output, JSON, MCP, and `budget_optimization_audit` use the corrected
  semantics; agent wording distinguishes backfill from insufficient history.
  PO-approved addition (B): `check` and `history` take the displayed price
  and moving averages from `effective_prices.json` observations, with
  explicit price provenance; `history.csv` remains only a cached-quote fallback.
- **AC-4 — EH-4 / [#29](https://github.com/parisneto/anticharon/issues/29): Redirect identity.**
  Preserve exact imported slugs and fallback order. Persist redirect/dynamic
  state and canonical identity when known; avoid repeated useless retries.
  Show `NOT_TRACKED` with a diagnostic in price tables. Never attribute
  stable historical prices to an unstable redirect identity.
- **AC-5 — EH-5 / [#28](https://github.com/parisneto/anticharon/issues/28): MCP resource.**
  Add read-only `anticharon://effective_prices.json`, MIME `application/json`.
  Return the local store, or `{}` when absent, without network or mutation.
  Document and test both existing-file and missing-file behavior.
- **AC-6 — EH-6 / [#30](https://github.com/parisneto/anticharon/issues/30): Batch discovery.**
  Normal discovery silently excludes IDs ending in `:batch`. The changelog
  explains asynchronous Batch API variants and the possible 24-hour delay.
  Exact `model add <slug>:batch` and explicitly configured Hermes batch
  slugs remain allowed, without rewriting or removal.
- **AC-7 — EH-7 / [#31](https://github.com/parisneto/anticharon/issues/31): CLI help.**
  Document consistent help syntax for every primary/nested command.
  Successful help exits 0 and shows command-specific options; invalid forms
  fail clearly or are supported consistently. Review top-level options
  without promoting unrelated options merely to mask help inconsistency.

## 3. Non-Goals

- Broad pre-v0.6 migration; deletion/replacement of user VM data as a workaround.
- Automatic Batch API submission/polling; provider-granular historical storage.
- Combining unrelated bug and enhancement work into one issue.

## 4. Evidence Gates

Keep current results only. PASS requires referenced revision/scope evidence;
relevant changes require revalidation.

| ID | Required proof | Current state/result | Evidence |
|---|---|---|---|
| E-1 | Protocol-update check before scope approval | PASS: checked 2026-10-02; `2026-07-28` is the current revision | [MCP versioning page](https://modelcontextprotocol.io/specification/versioning); PLAN.md, Protocol baseline check |
| E-2 | AC-1: mature day-0, insufficient and gapped history | PASS at `7673c81` (analytics + tracker scope, revalidated after W2; also duplicate dates, zero and invalid prices, observation-authoritative current price, unavailable baselines) | `tests/test_analytics.py`, `tests/test_tracker.py` (`first_seen` independence; run/fallback/history parity) |
| E-3 | AC-2: metadata, idempotence, default precedence, manual retention | PASS at `09ce27c` (sync, `list_models`, and check-output scope, including overlapping manual/Hermes slug; CLI `model list` renders the same `is_default`) | `tests/test_hermes_ownership.py` |
| E-4 | AC-3: CLI/MCP/prompt analytics parity | PASS at `7673c81` (run/history/CLI/MCP/prompt parity; price provenance; local reads from the store without `history.csv`) | `tests/test_analytics_parity.py`, `tests/test_tracker.py` |
| E-5 | AC-4: redirect persistence, retries, `NOT_TRACKED` output | PASS at `7bbb0cb` (first detection, 24h reuse, force, unresolved, dry run, local reads, human/JSON/MCP output) | `tests/test_redirect_identity.py` |
| E-6 | AC-5: present/missing local resource, no network or mutation | PASS at `f58caea` (also corrupt store → `{}`) | `tests/test_mcp_w4.py` |
| E-7 | AC-6: discovery exclusion and exact explicit add/import | PASS at `f58caea` | `tests/test_discovery.py`, `tests/test_manager.py`, `tests/test_hermes_ownership.py` |
| E-8 | AC-7: primary/nested help forms and exit codes | NOT_RUN | Pending |
| E-9 | Final deterministic suite, applicable quality checks, independent review | NOT_RUN | Pending |
| E-10 | Preserved-backup VM verification (D-8) | PARTIAL: Wave 1 scope (AC-1, AC-2) verified at `9683b66`; W2–W3 behavior not run on the VM | [vm_verification_wave1.md](evidence/vm_verification_wave1.md) |

## 5. Decisions

Keep stable IDs and current resolutions; reference rationale/approvals.
OPEN decisions block only dependent work.

| ID | Decision | Current resolution | Applies to |
|---|---|---|---|
| D-1 | Minimum valid observation coverage for maturity | RESOLVED: `effective_prices.json` is the only historical input to analytics (`history.csv` is a derived export; a separate current quote never overrides a stored observation dated today). `NEWLY_TRACKED` iff distinct valid observed dates in the 30-day window < `min_tracking_days_for_profile` (default 14). Valid = ISO date within the window, finite price ≥ 0 (zero allowed); each date counts once; gaps preserved; `first_seen` has no role; no coverage-span threshold. Unavailable comparison baselines stay unavailable | AC-1, Wave 1 |
| D-2 | Rename, repurpose, or replace `min_tracking_days_for_profile` | RESOLVED: key kept; means minimum distinct observed calendar days, including backfill; no rename, second key, or deprecation | AC-1, Wave 1 |
| D-3 | Manual-default preservation versus Hermes precedence | RESOLVED: a stored manual default preference is preserved while Hermes owns the effective default; only the effective default is `is_default`; authoritative removal restores the manual preference; temporary or incomplete detection preserves ownership | AC-2, Wave 1 |
| D-4 | Persisted redirect identity schema | RESOLVED: per-slug store entry `identity` (`exact`/`redirect`/`unresolved`), `resolved_id`, `identity_checked`; redirect = catalog lists exactly `~<slug>`; slug never rewritten; no canonical slug, backfill, or history for redirect/unresolved | AC-4, Wave 3 |
| D-5 | `NOT_TRACKED` JSON shape and stable message code | RESOLVED: `not_tracked` list (`model`, `status`, `identity`, `resolved_id`, `code`, `diagnostic`, `source`, `is_default`); codes `REDIRECT_IDENTITY` (info), `NO_EXACT_MATCH` (warning); no price shown (PO choice) | AC-4, Wave 3 |
| D-6 | Testable redirect retry/invalidation rule | RESOLVED: reuse stored redirect/unresolved state for 24h unless `run --force`; re-resolve afterwards; a slug now in the catalog is `exact` immediately | AC-4, Wave 3 |
| D-7 | Support `--help`, `help <command>`, or both consistently | OPEN | AC-7, Wave 4 |
| D-8 | Whether VM verification blocks completion | RESOLVED (PO, 2026-10-05): VM verification was completed with a preserved pre-v0.6.x shortlist; it covers Wave 1 only, see E-10 | E-10, Wave 4 |

## 6. Current Execution State

| Wave | Status | Blocking gate | PO action |
|---|---|---|---|
| W1 — Data contract (AC-1, AC-2) | IMPLEMENTED at `09ce27c`; independent re-review of audit remediation pending (E-9) | None for W2 start | Review W1; approve W2 start |
| W2 — Analytics propagation (AC-3 + B) | IMPLEMENTED at `7673c81`; independent review pending (E-9) | None | Review W2 |
| W3 — Identity and catalog boundaries | IMPLEMENTED at `7bbb0cb`; independent review pending (E-9) | None | Review W3 |
| W4 | NOT_STARTED | D-7, D-8 | Resolve D-7, D-8 before dependent work |

Preserve only current truth; reference everything else. At wave end, update
E-n, D-n, this row, and unresolved deferred items. Reference history rather
than copying it. Scope/acceptance changes require PO approval before implementation.

## 7. Deferred

- Hermes detection has no explicit "Hermes owns no default" signal (an unreadable default is treated as unavailable), so authoritative removal is honored at the sync boundary (`complete` with no models) but no detector emits it yet.
- Pre-existing lint debt is unchanged; changed-line gate passes against `219a766` (`docs/standards/lint_baseline_legacy.txt`).

Non-goals: §3; OPEN decisions: §5;
broader roadmap: [BACKLOG.md](../../BACKLOG.md). Reference existing owners.

## 8. Definition of Done

- AC-1…AC-7 proven by current E-2…E-8 evidence; E-1 check sourced before scope closes.
- Resolve dependent decisions; synchronize spec, examples, agent briefing,
  and changelog. Add bug regression tests.
- E-9: green `uv run pytest` and applicable checks; disclose changed/skipped
  expectations. Live tests remain opt-in. E-10 follows approved D-8.
- Review behavior against linked issues. Follow AGENTS.md for independent
  review, SemVer, changelog closeout, release notes, and PO release sign-off.
- Mark current state complete with evidence references. Integration/tagging/
  pushing retain existing authority.
