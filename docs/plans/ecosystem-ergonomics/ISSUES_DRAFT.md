# GitHub Issues Draft — Ecosystem Ergonomics & MCP Discoverability (v0.6.0 Beta)

> Companion to [`EXECUTION_CONTRACT.md`](EXECUTION_CONTRACT.md) (scope closed
> 2026-09-24). Each section is the issue body created on GitHub. Ledger IDs
> (`A2A-1`, `D-19`, `F-15`, …) point to the canonical ledger. All 12 issues
> were created before Wave 1; actual GitHub issue numbers are recorded in §10
> of the ledger and in the final column of the map below. Draft IDs are stable
> planning references, not GitHub issue numbers.

Protocol baseline for every issue: MCP specification `2026-07-28`
(https://modelcontextprotocol.io/specification/2026-07-28).

## Issue map & order

The draft IDs below are stable planning references only. The execution control
plane reads actual GitHub issue numbers from §10 of the canonical ledger; the
issue-registration gate is complete.

| Draft ID | Title | Labels | Depends on (draft IDs) | GitHub issue # |
|---|---|---|---|---|
| 1 | Unified agent message contract (`messages` + `isError`) | enhancement, a2a | — | #12 |
| 2 | Separate `check` / `history` / `run` with persisted alerts | enhancement, breaking | 1 | #13 |
| 3 | Source-tagged shortlist, Hermes order and explicit defaults | enhancement, bug | 1 | #14 |
| 4 | Exact-match slugs: no silent drops or substitutions | bug | 1 | #15 |
| 5 | CLI/MCP parity tools: shortlist, calibration, self-test, conditional OpenClaw import | enhancement | 1, 3 | #16 |
| 6 | MCP tool annotations, server identity and descriptions | enhancement, mcp | 2, 5 | #17 |
| 7 | Prompt parity on the CLI and prompt hardening | enhancement, docs | 5 | #18 |
| 8 | Fallback-aware alerts and fallback-order display (spike first) | enhancement | 2, 3 | #19 |
| 9 | Experimental self-update: `check_updates` + `run_update` | enhancement, experimental | 1 | #20 |
| 10 | Documentation truth pass: single `llms.txt`, install docs, Beta, agent skill | docs | 1–9 (content) | #21 |
| 11 | Governance: protocol-baseline rule, pre-work cleanup | docs, chore | — | #22 |
| 12 | Release v0.6.0 Beta: manual gates and sign-off | release | all | #23 |

---

## 1. Unified agent message contract (`messages` + `isError`)

**Labels:** enhancement, a2a · **Ledger:** WS-A2A (A2A-1…8), §3c, §3d, D-1, D-1b, D-1c, D-1d, F-1, F-14, F-17, F-20

Foundation for every other issue: one agent-readable channel for all CLI
`--json` and MCP responses.

**Scope**
- `AgentMessage` (`level` info/warning/error, `code`, `text`, optional
  `action` `{mcp, cli}`, optional `model`); every response carries `status`,
  `messages` (never empty — at least `COMPLETED` with elapsed time) and
  `elapsed_ms`.
- `status` ∈ {`error`, `refused`} → MCP `isError: true` / CLI exit code 1
  (spec 2026-07-28, Tools → Error Handling).
- One CLI renderer for messages (stderr in MCP mode).
- Clean break: remove `notice`, `hint`, top-level `message`, Hermes
  `warning` keys and top-level `error`; keep `status`, `_hints`,
  `price_warnings[].message`, per-check `error` in `test`.
- Rename `priceWarnings` → `price_warnings`.
- `HERMES_DIVERGENT` surfaced in `run`/`check` (not only `test`); dry-run
  wording via `PREVIEW_ONLY` / `SHORTLIST_UPDATED`.

**Acceptance:** §6 WS-A2A; catalog in §3d documented in `llms.txt` and spec
§10; tests migrated from removed keys to message codes (disclosed, Rule 8).

---

## 2. Separate `check` / `history` / `run` with persisted alerts

**Labels:** enhancement, breaking · **Ledger:** MCP-10, MCP-11, D-3, D-4, D-18, D-18b, D-18c, D-19, D-22, D-28, §3a · **Depends on:** #12

**Scope**
- `check` / `check_prices`: local read of latest prices (`history.csv`) and
  persisted alerts (`alerts.json`); no network, no recalculation, no `--zdr`;
  `DATA_STALE` when older than today.
- `history` / `get_model_history`: local 30-day read (`effective_prices.json`)
  owning all analytics/profiles (`check --profile` moves here).
- `run` / new `run_prices`: the only fetch-and-write path; writes
  `history.csv`, `effective_prices.json`, `alerts.json`; `--model`,
  `--dry-run` (opt-out, default saves), `--force` (replaces `force_refresh`),
  `--zdr` (live-only, never persisted); same-day rule.
- Alerts computed at persist time, decoupled from fetch; single-model runs
  recompute cross-model alerts from stored prices.
- Spec §5 → "Three Files, Three Lifecycles"; §7 and §10 updated.

**Acceptance:** §6 WS-MCP + CLI ↔ MCP parity (zero-network test for local
reads; parity test).

---

## 3. Source-tagged shortlist, Hermes order and explicit defaults

**Labels:** enhancement, bug · **Ledger:** MCP-7, D-2, D-5, D-13, D-15, D-24, D-25, F-2, F-10, F-19, DOC-4 · **Depends on:** #12

**Scope**
- Shortlist entries `{"model", "source", "order"?}`; flat lists migrate on
  next write.
- Manual adds survive Hermes sync (fixes F-2); removing a Hermes entry is
  refused (`SOURCE_MANAGED`, `isError`).
- Hermes order persisted (`order` 0 = default); divergence compared
  order-sensitively against Hermes entries only.
- Default never inferred from position (fixes F-19); `model add --default` /
  `add_model(default=true)`; Hermes default wins automatically.
- No default → `NO_DEFAULT` message, no ★, no default-based alerts.
- Close the pre-plan "divergence in `--json`" item as already fixed, with a
  CLI vs `--json` parity regression test.

**Acceptance:** §6 WS-MCP; regression tests F-2, F-10, F-19.

---

## 4. Exact-match slugs: no silent drops or substitutions

**GitHub issue:** #15 · **Labels:** bug · **Ledger:** MCP-2, MCP-6, MCP-8, D-4b, D-14, F-3, F-15, F-16 · **Depends on:** #12

**Scope**
- Exact slug match in every major operation; fuzzy matching only in
  discovery/filters.
- Remove the `startswith` prefix fallback in `run_tracker` (F-16).
- The three silent skip paths emit per-model `NO_EXACT_MATCH` /
  `PRICE_UNAVAILABLE` / `PRICE_INVALID` (F-15).
- `get_model_history` is local-only: exact slug absent from the shortlist
  returns `NOT_MONITORED`; it does not query OpenRouter. `run --model` is an
  exact filter over the configured shortlist: if absent, it refuses with
  `NOT_MONITORED` and performs no catalog lookup or pricing fetch. `add_model`
  is the separate exact catalog-validation operation; an invalid/nonexistent
  slug returns `NO_EXACT_MATCH`. No path substitutes a similar slug.
- Surface the already-stored `canonical_slug` from `effective_prices.json`
  in JSON (key = exact shortlist slug).

**Acceptance:** fixture regressions prove: a shortlisted exact `run --model`
fetches only that model; an absent target is refused as `NOT_MONITORED` with no
catalog/pricing network call; `add_model` refuses an invalid exact slug as
`NO_EXACT_MATCH`; and no model is silently dropped or substituted.

---

## 5. CLI/MCP parity tools: shortlist, calibration, self-test, conditional OpenClaw import

**Labels:** enhancement · **Ledger:** MCP-1, MCP-5, MCP-13, D-6, D-12, D-17, D-29, A-1 · **Depends on:** #12, #14

**Scope**
- `add_model` / `remove_model` / `list_models` (wrap `manager`); defaults
  match the CLI (persist; `dry_run=true` opts out).
- `add_model` refuses when the catalog is unreachable
  (`CATALOG_UNAVAILABLE`, cause stated, retry later).
- `calibrate_token_weights` accepts a CSV path accessible to the MCP server
  and uses the CLI-equivalent parser; CSV bytes are not uploaded over MCP
  (A-1). `calibrate_fast` accepts the three validated resulting weights.
  Both use the shared persistence implementation, save by default, accept
  `dry_run=true` as the no-write option, save prior weights to `.bak`, and
  return outcome/messages.
- Add the calibration-details MCP resource with component definitions,
  sample log lines, derivation guidance for `calibrate_fast`, and the CLI
  fallback when the source CSV is not available to the MCP server.
- `self_test` wrapping `tester.py`.
- Conditional alpha `import_openclaw_models` plus CLI equivalent, only if the
  supported OpenClaw version/output and first acceptance case are verified.
  Follow the fail-closed constraints in `openclaw_research.md`; otherwise
  park it. The specific supported version, output schema, and selected-agent
  acceptance case remain OPEN until evidence and PO confirmation.

**Acceptance:** calibration persistence, input validation and outcomes match
the ledger; D-12, D-13, D-25 enforced. For OpenClaw, include the verified
version/schema fixture and incomplete-result protection, or record the
importer as parked.

---

## 6. MCP tool annotations, server identity and descriptions

**Labels:** enhancement, mcp · **Ledger:** MCP-3, MCP-4, MCP-9, §3b (ANN-1…4), D-17, D-23, F-6, F-18 · **Depends on:** #13, #16

**Scope**
- All five `ToolAnnotations` fields on every tool, per the MCP-9 table
  (worst-case capability); test fails on a missing annotation.
- `MCPServer(version=__version__, instructions=…)`.
- Tool descriptions state side effects, network behavior, enum values, and
  point to `anticharon://llms.txt`.
- Spec §10: session-risk note (open-world tools, untrusted catalog text,
  `run_update` executes commands); `_meta` only for namespaced metadata.
- Draft SEPs tracked, not shipped (ANN-5).

**Acceptance:** `serverInfo.version` equals `__version__`; annotation test.

---

## 7. Prompt parity on the CLI and prompt hardening

**Labels:** enhancement, docs · **Ledger:** MCP-12, DOC-2, F-13 · **Depends on:** #16

**Scope**
- Prompt templates in one shared module; CLI `anticharon prompt …` renders
  the same guides.
- Prompts reference MCP tools instead of CLI/Hermes commands where an MCP
  path exists; "call `check_prices` / read `anticharon://llms.txt` before
  trusting a remembered default model".

**Acceptance:** parity test covers prompts.

---

## 8. Fallback-aware alerts and fallback-order display (spike first)

**Labels:** enhancement · **Ledger:** MCP-14, E-5, D-5 · **Depends on:** #13, #14

**Scope**
- Spike E-5: prototype price order vs Hermes fallback order with real data;
  PO confirms display and thresholds.
- Alert describing the next fallback relative to the default, persisted in
  `alerts.json`, suppressed when no default exists.

**Acceptance:** E-5 evidence recorded in the ledger before merge.

---

## 9. Experimental self-update: `check_updates` + `run_update`

**Labels:** enhancement, experimental · **Ledger:** WS-SELFUP (SELFUP-0…2), E-1…E-4, D-9, D-9b, D-26, D-27 · **Depends on:** #12

**Scope**
- `check_updates` / `check-updates`: user-initiated only; installed
  `__version__` vs GitHub `releases/latest`; ~2 s timeout; `is_latest`.
- `run_update` / `update --type`: always `EXPERIMENTAL`; named types
  (`install_only`, `restart_host`, `phoenix`, `phoenix_inverted`,
  `reload_request`); `uv tool install --force git+…`, fallback
  `sys.executable -m pip install --force-reinstall git+…`.
- Final type set and mechanics chosen from PO live tests during
  development; no personal paths (`~`/`$HOME` or self-discovery).
- Evidence gates E-1…E-4 recorded in the ledger.

**Acceptance:** §6 WS-SELFUP; subprocess layer mocked in tests; no network in
the default suite.

---

## 10. Documentation truth pass: single `llms.txt`, install docs, Beta, agent skill

**GitHub issue:** #21 · **Labels:** docs · **Ledger:** DOC-1, DOC-3, DOC-3a, DOC-5, DOC-7, D-7, D-8, D-27, F-7, F-8, F-9, F-11 · **Depends on:** #12, #13, #14, #15, #16, #17, #18, #19, #20

**Scope**
- Single repo-root `llms.txt` shipped into the wheel
  (`[tool.hatch.build.targets.wheel.force-include]`); delete the package
  copy; CI asserts it is in the wheel.
- Regenerate `llms.txt`; fix spec §5/§6/§7/§10 and BACKLOG Milestone 3.
- Install docs: `uv tool install` and `pip install` only (remove all `uvx`
  snippets); `~`/`$HOME` paths; per-host notes.
- Beta declaration (README, `llms.txt`, CHANGELOG, release notes draft,
  `Development Status :: 4 - Beta` classifier).
- Thin `.agents/skills/anticharon/SKILL.md` for agents installing Anticharon.
- Optional advisory use of `scripts/supplemental_version_inventory.py`; its
  generated report stays under `.local/`, is reviewed by a human, and is not a
  CI gate.
- Inventory version-like strings in user-facing documentation/discovery
  surfaces; classify current, historical, dependency, and unrelated values.
  Correct or explain confirmed stale claims; a regex match alone is not a
  removal instruction.

**Acceptance:** `llms.txt` version test; registry-vs-docs drift test; wheel
check in CI; every flagged user-facing version string has a disposition in the
ledger before release. Historical and third-party versions are preserved
unless there is a separate reason to change them.

---

## 11. Governance: protocol-baseline rule, pre-work cleanup

**Labels:** docs, chore · **Ledger:** DOC-6, DOC-8, §3c

**Scope**
- `AGENTS.md` Rule 4: every sprint ledger pins the MCP spec baseline and
  records a protocol-update check; PR descriptions cite it.
- Move `docs/specs/pre-work/draft_eval_harness.md` to `.local/`, remove
  `docs/specs/pre-work/`, reword the BACKLOG eval-harness link.

---

## 12. Release v0.6.0 Beta: manual gates and sign-off

**Labels:** release · **Ledger:** §6 Manual release gates, Release governance · **Depends on:** #12, #13, #14, #15, #16, #17, #18, #19, #20, #21, #22

**Checklist**
- [ ] `uv run pytest` green (< 30 s), lint gate per the linting skill.
- [ ] MG-1 `scripts/inspect_mcp.sh` walkthrough and Tools/Prompts/Resources
      checklist recorded in the ledger; no screenshots required.
- [ ] MG-3 `hermes mcp test anticharon` recorded (baseline v0.5.5: 4 tools,
      2441 ms; expected: every tool in the §3a parity matrix).
- [ ] Rule 11 version bump (`pyproject.toml`, `__init__.py`, README,
      CHANGELOG, `llms.txt`) in one commit.
- [ ] BACKLOG updated (calibrate item done, Milestone 3 fixed, parked items
      added).
- [ ] Release notes draft in `.local/`.
- [ ] MG-2 PO sign-off recorded; only then tag and push (Rule 11).
