# Mandatory Execution Contract — Ecosystem Ergonomics & MCP Discoverability

> Sole planning document for this sprint (same single-document format as
> `docs/plans/post-launch-sprint-1/EXECUTION_CONTRACT.md`). It MUST stay
> synchronized with the implementation; any material change to scope,
> acceptance criteria, non-goals, evidence gates, or testing strategy MUST
> update this document in the same change. Scope is closed: every decision
> in §5 is decided, resolved, parked or tracked; the only items deliberately
> left to development are named in §5 ("Decided during development") and
> are settled by evidence gates or PO live tests, never guessed.

Written by: parisneto (Product Owner) + planning agent
Status: **SCOPE CLOSED — issues registered; execution governed by §10** (PO refinement complete, 2026-09-24; issue register and D-14 clarified 2026-09-25)
Last synchronized: 2026-09-25 (GitHub issues #12–#23 registered; D-14/D-18c clarified; version inventory helper recorded; W1 started, D-1e decided)
Base commit: `main` @ `1a64782` (includes the `ci.yml` read-only-token change; no effect on scope)
Target version: `0.6.0` — **Beta** (D-10, D-20); breaking interface changes are allowed until real users/feedback exist
Tracking: GitHub issues #12–#23 are created and registered in §10. Formal blocker relationships are set on GitHub. Wave handoffs are routing notes; this ledger is authoritative.

Protocol baseline: **MCP specification `2026-07-28`**
(https://modelcontextprotocol.io/specification/2026-07-28 — schema
`schema/2026-07-28/schema.ts` in `modelcontextprotocol/modelcontextprotocol`),
verified 2026-09-24. See §3c.

---

## Document set

| Input | Role |
|---|---|
| Pre-plan "Ecosystem Ergonomics & MCP Discoverability" (PO, private) | Primary scope source (objectives 1–3) |
| Feature request "Industry-standard auto-update mechanism for long-running MCP server" (PO, private) | Detailed design input for WS-SELFUP |
| Prior PO planning session, final candidate list `a1`–`a6` (private chat, pasted by PO 2026-09-23) | Reconciled into F-14…F-17, A2A-6/7, MCP-6/7, DOC-2, CAND-7/8 |
| `docs/BACKLOG.md` | Secondary source — **only** items aligned with the two documents above are pulled in (PO rule, 2026-09-23) |

The two private input documents are **not** promoted (D-11): their content is
fully incorporated into this ledger, which is the self-contained public
record.

---

## 1. Scope Chosen for This Sprint

Goal: an autonomous agent connected over MCP can **discover** Anticharon's
surface, **manage** its shortlist, **understand** every response without
guessing, and **learn it is out of date** — without dropping to the CLI.

| WS | Workstream | Source |
|---|---|---|
| WS-A2A | Agent-to-agent message contract (`messages`) shared by JSON and CLI output | PO directive (2026-09-23) + pre-plan §3 in-band notifications |
| WS-MCP | MCP tool layer & CLI parity: `check`/`history`/`run` separation, source-tagged shortlist with Hermes order and explicit defaults, exact-match slugs, no silent drops, persisted alerts, annotations, new tools (`run_prices`, `add_model`, `remove_model`, `list_models`, `calibrate_token_weights`, `calibrate_fast`, `self_test`), conditional OpenClaw importer, prompt parity | Pre-plan §1 + BACKLOG + grill decisions + [`openclaw_research.md`](openclaw_research.md) |
| WS-DOC | Documentation & discoverability: single `llms.txt`, prompts, install docs (no `uvx`), agent skill, divergence bug, Beta declaration, protocol-baseline governance, pre-work cleanup | Pre-plan §2 + PO review |
| WS-SELFUP | Self-update infrastructure, user-initiated and experimental: `check_updates` + `run_update` | Pre-plan §3 + self-update feature request (automatic checks parked) |

Work-item IDs use the workstream prefix (`A2A-1`, `MCP-2`, `DOC-3`,
`SELFUP-0`); evidence gates are `E-n`, decisions `D-n`, findings `F-n`,
out-of-scope candidates `CAND-n`.

BACKLOG alignment review (only items passing the PO rule are included):

| BACKLOG item | Decision | Reason |
|---|---|---|
| Expose `calibrate` as MCP tool (`calibrate_token_weights`) | **IN** (MCP-5) | Same goal: agents manage config natively over MCP; same mutation contract as MCP-1 |
| Interactive CLI shortlist picker | OUT | CLI TUI, opposite direction from "no CLI needed" |
| Universal one-way shortlist importers | OUT (design constraint IN) | Shares the shortlist-write path with MCP-1 and `import_hermes_models`. The parsers (LiteLLM, Cursor, Claude Code, OpenRouter collections) stay out; but D-2 must define shortlist authority for **any** writer (manual add, Hermes sync, future importers), so importers plug in later without re-deciding it. |
| Eval harness & EDD gate | OUT (draft relocated by DOC-6) | Own engine and effort. Its §4 user stories were re-read for ergonomics features — see CAND-5. |
| Model metadata & comparator | OUT | New analytics domain |
| Negative-token-count hardening, TraceLab default cache rate, Pareto cutoff, provider-granular persistence, legacy lint debt | OUT | Pricing-engine domain, unrelated to ecosystem ergonomics |

---

## 2. Cross-Check Findings (repo @ `1a64782`, v0.5.5)

Evidence gathered during planning; each finding is bound to a work item.

| ID | Finding | Evidence | Bound to |
|---|---|---|---|
| F-1 | **No uniform in-band message channel.** Payloads use ad-hoc keys: `message` (`manager.ManagementResult`, `import_hermes_models` warning path), `notice` (`import_hermes_models`), `warning` (`hermes_integration`, `import_hermes_models`), `hint` / `_hints`, `error`, and `priceWarnings[].message`. Casing is also mixed (`priceWarnings` vs snake_case everywhere else). | `src/anticharon/models.py` (`PriceWarning`, `TrackerResult.to_dict`), `src/anticharon/mcp.py:146-215`, `src/anticharon/manager.py:12-30` | WS-A2A |
| F-2 | **Hermes sync silently reverts shortlist mutations.** With a `complete` Hermes detection, `run_tracker(dry_run=False)` overwrites `shortlist.json` with the Hermes set and always tracks the Hermes set, so a model added via `model add` (and via the new MCP `add_model`) is dropped on the next `run`/cron. | `src/anticharon/tracker.py:318-340`, `src/anticharon/hermes.py` `sync_hermes_to_config` (`changed = current_shortlist != new_models`) | D-2 (blocks MCP-1) |
| F-3 | `get_model_history` filters by **substring** and returns an empty list silently for an unknown model; a short query can also match several models. | `src/anticharon/mcp.py:97-104` | MCP-2 |
| F-4 | `get_model_history`'s description claims "from local history.csv storage", but the JSON path calls `run_tracker`, which performs a **live OpenRouter fetch** (10 s timeout) and Hermes detection. | `src/anticharon/mcp.py:92-96`, `src/anticharon/tracker.py` (`fetch_openrouter_models`) | MCP-3, D-4 |
| F-5 | `check_prices(force_refresh=True)` only raises the timeout 10 s → 15 s. Spec §10.2 says it "ignor[es] local cache". Doc and behavior disagree. | `src/anticharon/mcp.py:55-62`, `docs/specs/spec_v1_anticharon.md` §10.2 | D-3 |
| F-6 | MCP server is created as `MCPServer("anticharon")` — no `version` and no `instructions`. The installed SDK (`mcp` 2.2.0, `MCPServer`) supports both. `instructions` is a server-level channel hosts inject into the model context — a natural home for "fetch `anticharon://llms.txt` / call `check_prices` before trusting memory". | `src/anticharon/mcp.py:31`; `MCPServer.__init__` signature | MCP-4, DOC-2 |
| F-7 | Spec §10.1 says `mcp>=1.3.0 (FastMCP)`; runtime resolves `mcp` 2.2.0 `MCPServer` (the FastMCP import is only a fallback). | `pyproject.toml`, `src/anticharon/mcp.py:14-17` | DOC-1 |
| F-8 | `llms.txt` (root and package copy, identical) is stale: header `v0.3.2`, `check_prices` signature omits `zdr_only`, no prompts listed, CLI-first framing. | `llms.txt`, `src/anticharon/llms.txt` | DOC-1 |
| F-9 | `docs/BACKLOG.md` Milestone 3 lists resources that do not exist (`anticharon://shortlist`, `anticharon://profiles`) and a prompt not in code ("Gemini 3.7 vs 3.8 case study"). Real: `anticharon://llms.txt`, `anticharon://history.csv`, `anticharon://shortlist.json`; 5 prompts. | `docs/BACKLOG.md`, `src/anticharon/mcp.py:224-356` | DOC-1 |
| F-10 | **Divergence bug as described is already fixed** (Issue #4, v0.5.5): `--json` carries `shortlist_divergence` and `warning`. Residual: the comparison is order-sensitive (`list(h_models) != list(persisted)`) and covers the whole shortlist. Per D-5, order-sensitivity is **correct** (Hermes fallback order matters); only the scope changes to Hermes-sourced entries. | `src/anticharon/tester.py:104-127` | DOC-4, D-5 |
| F-11 | *(Resolved by D-27: `uvx` unsupported.)* All README host snippets use `uvx --from git+…`; none use `uv tool install` + absolute binary path. `uvx` users are **not** upgraded by `uv tool upgrade`. GUI hosts (Claude Desktop) do not inherit the shell `PATH`, so `~/.local/bin` must be an absolute path. | `README.md` §"Model Context Protocol (MCP) Server" | DOC-3, E-2 |
| F-12 | Distribution is git-only (no PyPI). GitHub Releases exist with `v0.5.5` marked Latest (`v0.5.4` has a tag but no Release), so `releases/latest` is a usable version source. | `gh release list` | E-4 |
| F-13 | `mcp.py` prompts hard-code Hermes commands (`hermes config set model.default …`) and CLI commands (`anticharon model add`) instead of the MCP tools this sprint adds. | `src/anticharon/mcp.py:277-356` | DOC-2 |
| F-14 | (`a1`) `check`/`run` human and `--json` output never report Hermes ↔ shortlist divergence; only `anticharon test` computes it. `HermesIntegrationStatus.warning` is set only for `incomplete` detection. | `src/anticharon/tracker.py:318-340`, `src/anticharon/tester.py:107` (only divergence computation in `src/`) | A2A-6 |
| F-15 | (`a2`) **Silent model drops.** Three `continue` paths in `run_tracker`'s per-model loop — slug not in catalog, missing advertised price, invalid/sentinel listed price — skip a shortlisted model with no warning in human output, `--json`, MCP, or chart. Hermes sync persists unvalidated slugs, so the `anticharon test` divergence check cannot catch it (counts match). | `src/anticharon/tracker.py:431-454` | MCP-6 |
| F-16 | **Silent model substitution.** When the exact slug is missing, `run_tracker` falls back to the first catalog key that `startswith(model_id)` — e.g. a retired `…-flash` can silently be priced as `…-flash-lite` — with no signal to the user. Found while verifying F-15. | `src/anticharon/tracker.py:433-435` | MCP-6, D-14 |
| F-17 | (`a3`) `check` prints "Hermes: Synced (N models …)" even in dry-run, where nothing is persisted; `model sync` already uses `[DRY RUN] Would…` phrasing. | `src/anticharon/cli.py:46`, `src/anticharon/cli.py:138` | A2A-7 |
| F-18 | **No MCP tool annotations.** No tool declares `readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`. Per the MCP spec defaults, un-annotated tools are treated as non-read-only, potentially destructive, non-idempotent, open-world — so hosts may over-prompt, and some app directories require them. The installed SDK supports `annotations=ToolAnnotations(...)` on `@server.tool`. Source: MCP blog "Tool Annotations" (2026-03-16); surfaced while checking `_hints` (PO, 2026-09-24). | `src/anticharon/mcp.py` (all `@server.tool`), `mcp.types.ToolAnnotations` | MCP-9 |
| F-19 | **Implicit default by position.** The "default" model is always `shortlist[0]` — it gets the `★ [DEFAULT]` badge and is the `BEST_OPTION_CHANGED` baseline — even in standalone mode with no Hermes, where the first manually added model silently becomes "the default". | `src/anticharon/tracker.py:604-615`, `src/anticharon/cli.py:85`, `src/anticharon/cli.py:532`, `src/anticharon/chart.py:88` | D-5 |
| F-20 | **Errors are not flagged as tool execution errors.** Spec 2026-07-28 (Tools → Error Handling): API failures, input validation and business-logic errors SHOULD be returned in the tool result with `isError: true` so clients pass them to the model for self-correction. Anticharon's MCP tools return error/refused/warning payloads as ordinary results. | `src/anticharon/mcp.py` (all tools); spec 2026-07-28 `server/tools` | A2A-2 |

---

## 3. Workstreams & Work Items

### WS-A2A — Unified Agent-Message Contract (foundation; lands first)

PO directive: one `messages` channel for talking to agents, backed by
classes that also render CLI output. Contract approved as §3d (D-1).

- **A2A-1 `AgentMessage` dataclass** in `src/anticharon/models.py`: `level`
  (`info` | `warning` | `error`), `code` (catalog in §3d), `text`, optional
  `action` (`{"mcp": …, "cli": …}`), optional `model`. `to_dict()` for JSON.
- **A2A-2 Envelope rule** (D-1b): every JSON payload (CLI `--json` and every
  MCP tool) carries `status`, `messages` (always present, never empty —
  at least `COMPLETED`), and `elapsed_ms`.
- **A2A-3 `isError` mapping** (F-20, §3c): `status` ∈ {`error`, `refused`}
  → MCP tool execution error (`isError: true`) with the same JSON body; CLI
  exit code 1. Everything else is a normal result.
- **A2A-4 CLI renderer:** one flat function renders `messages` for human
  output (stderr in MCP mode per ADR 0001). Replaces the ad-hoc
  `print(f"… {res.message}")` / `notice` strings.
- **A2A-5 Legacy keys removed** (D-1c, clean break): `notice`, `hint`,
  top-level `message`, `hermes_integration.warning` / `model sync`
  `warning`, top-level `error` → `messages`. `status`, `_hints` (D-1d),
  `price_warnings[].message` and per-check `error` in `test` stay.
- **A2A-6 Divergence everywhere** (F-14, D-5): `run`, `check` and
  `check_prices` emit `HERMES_DIVERGENT` when the Hermes sequence differs
  (order-sensitive) from the Hermes-sourced shortlist entries; one shared
  function with `anticharon test`.
- **A2A-7 Dry-run wording** (F-17): status lines distinguish "used for this
  run" from "persisted" via `PREVIEW_ONLY` / `SHORTLIST_UPDATED`.
- **A2A-8 Rename `priceWarnings` → `price_warnings`** (D-1c, ex-CAND-3):
  snake_case consistency across all JSON; clean break in `0.6.0`.
- `_meta` is never the agent channel (ANN-3); no `_meta` mirroring of
  messages this sprint.

### WS-MCP — MCP Tool-Layer Hardening

- **MCP-1 `add_model` / `remove_model` MCP tools** — thin wrappers over
  existing `manager.add_model` / `manager.remove_model` (already used by the
  CLI, `src/anticharon/cli.py:28`). Defaults match the CLI (persist;
  `dry_run=true` opts out — D-29). `add_model` accepts `default=true`
  (D-25). Manual adds are never reverted by sync (D-2, MCP-7); removing a
  non-`manual` entry is refused with `SOURCE_MANAGED` (D-13).
  Scenarios covered (not Hermes-only):
  1. Standalone MCP host, no Hermes (Claude Desktop, Cursor, Antigravity,
     MCP Inspector) — primary beneficiary; add/remove persist.
  2. Hermes detected, `complete` — governed by D-2.
  3. Hermes detected, `incomplete` — persisted shortlist is authoritative
     (spec §6.2 sync protection); add/remove persist.
  4. `--no-hermes` / CLI `model add` — unchanged, same `manager` path.
  5. Catalog unreachable (`validate_catalog` needs a live fetch) — not
     persisted; error + `CATALOG_UNAVAILABLE` naming the external failure,
     action "retry later" (D-12).
  6. Already-present / not-present slugs — idempotent results; only
     surrounding whitespace is trimmed, the slug itself must match exactly
     (D-14; no suffix stripping).
- **MCP-2 Fail loudly in `get_model_history`** (D-4b, D-14): exact slug
  only; this is a local read and does not query the catalog. Slug in
  shortlist → history; slug absent from shortlist → `status: "not_monitored"`
  + `NOT_MONITORED` (action `add_model`, which validates against OpenRouter).
  It never emits `NO_EXACT_MATCH`; matching rule written into spec §10.2.
- **MCP-3 Docstring/description hardening** for every tool: state side
  effects (e.g. `run_prices` writes `history.csv`, `effective_prices.json`,
  `alerts.json` and syncs Hermes entries unless `dry_run=true`), network
  behavior (local vs OpenRouter/GitHub), named enum values, and point to
  `anticharon://llms.txt` as the authoritative glossary.
- **MCP-4 Server identity**: pass `version=__version__` and an `instructions`
  string (short: what Anticharon is, "read `anticharon://llms.txt`", "call
  `check_prices` before recommending a default model"). Host support for
  `instructions` is checked in E-1.
- **MCP-5 `calibrate_token_weights` / `calibrate_fast` MCP tools** (BACKLOG
  item): `calibrate_token_weights` runs the full CLI-equivalent parser against
  a CSV path accessible to the MCP server; CSV bytes are not transported
  through MCP (A-1, D-6). `calibrate_fast` accepts the three host-derived
  component weights. The calibration resource explains how to derive them
  and points to CLI `calibrate` when the log is not accessible to the server.
  Both persist by default (`dry_run=true` opts out, D-29), save prior weights
  to a `.bak` next to `shortlist.json` (D-17), and return computed weights,
  backup path, and `messages`.
- **MCP-6 No silent drops or substitutions** (F-15, F-16): each of the three
  skip paths emits a per-model message (`NO_EXACT_MATCH`,
  `PRICE_UNAVAILABLE`, `PRICE_INVALID`) in CLI, `--json` and MCP; the
  `startswith` prefix fallback in `run_tracker` is removed (D-14);
  `NO_EXACT_MATCH` carries the `discover_models` retry action. Regression test
  reproduces the prior session's fake-slug scenario with fixtures (no live
  Hermes needed).
- **MCP-7 Source-tagged shortlist** (D-2, D-5, D-15, D-25, F-19): entries
  become `{"model", "source", "order"?}`; `source` ∈ `hermes` | `manual` |
  later `import:<name>`. Hermes sync replaces only `hermes` entries and
  preserves Hermes order (`order` 0 = Hermes default, 1…n = fallbacks);
  `manual` entries persist until removed; a manual default is `order` 0 on a
  `manual` entry, refused while a Hermes default exists. The default is
  never inferred from list position. Legacy flat lists migrate on next
  write. CLI (`model list`, TUI chart) and JSON surface `source`/default.
- **MCP-8 Surface `canonical_slug`** (D-14; corrected 2026-09-24): it is
  **already persisted** per model in `effective_prices.json`
  (`src/anticharon/tracker.py:274-276`, spec §5.2), under a top-level key
  equal to the shortlist slug — e.g.
  `"openai/gpt-5.6-luna": {"canonical_slug": "openai/gpt-5.6-luna-20260709", …}`.
  That is all that is needed (PO): **no new storage**, no field on the
  shortlist entry. Work: guarantee the `effective_prices.json` key is the
  exact shortlist slug (D-14), and surface `canonical_slug` in JSON outputs
  (`check`, `history`, `list_models`) read from that store. Re-keying
  history by `canonical_slug` (D-16 policy) stays **parked**.
- **MCP-9 MCP tool annotations** (F-18, D-17, D-23): every tool declares
  all five `ToolAnnotations` fields (`title` + four hints, ANN-1),
  describing its **worst-case capability** (not its `dry_run` default):

  | Tool | readOnly | destructive | idempotent | openWorld |
  |---|---|---|---|---|
  | `check_prices` | true | false | true | false (local read, D-19) |
  | `run_prices` | false | false | true | true |
  | `get_model_history` | true | false | true | false (local read, D-4) |
  | `discover_models` | true | false | true | true |
  | `import_hermes_models` | false | false | true | false |
  | `import_openclaw_models` (conditional alpha) | false | false | true | true |
  | `add_model` | false | false | true | true |
  | `remove_model` | false | true | true | false |
  | `calibrate_token_weights` | false | false (previous weights saved to `.bak`, D-17) | true | false |
  | `calibrate_fast` | false | false (previous weights saved to `.bak`, D-17) | true | false |
  | `list_models` | true | false | true | false |
  | `self_test` | false (writes and deletes a probe file in the data dir) | false | true | true (OpenRouter reachability) |
  | `check_updates` | true | false | true | true |
  | `run_update` | false | true | false | true |

  A test enumerates registered tools and fails if any lacks annotations.
- **MCP-10 Persist-on-observe** (D-18): price observations fetched for any
  shortlisted model are written to `history.csv` / `effective_prices.json`
  whenever they are obtained, per model; a full-shortlist update skips
  models already refreshed today (same-day rule); mixed per-model recency is
  valid state. Surfaces and parameters per D-18b / D-18c.
- **MCP-11 Command separation & parity** (D-19, D-20): implement §3a —
  `check`/`check_prices` become local latest-price reads from `history.csv`,
  displaying the alerts **persisted by the last `run` in `alerts.json`**
  (D-22; no recalculation, no `--zdr` — D-28;
  `DATA_STALE` message with a `run` action when the latest observation is
  older than today); spec §5 updated to three files in the same change;
  `history`/`get_model_history` become local 30-day reads from
  `effective_prices.json` and own all analytics/profiles (`check --profile`
  moves to `history`); `run`/`run_prices` is the only fetch-and-write path —
  it updates `history.csv` **and** `effective_prices.json`, computes and
  persists alerts from both, honoring the same-day rule, `--force`,
  `--model`, `--dry-run`. The hard-wired `check --dry-run` default is
  removed. A parity test enumerates CLI subcommands/arguments and MCP
  tools/parameters and fails on any mapping not in §3a or any unregistered
  asymmetry.
- **MCP-12 Prompt parity** (A-2 reversed by PO): the five prompts are
  business-case user guides, not an MCP-only feature. Prompt templates move
  to one shared module (single source) and are exposed on the CLI (e.g.
  `anticharon prompt list` / `anticharon prompt <name> [--arg value]`,
  printing the rendered guide; exact syntax recorded when built, D-21).
  A parity test covers all five shared prompt templates.

- **MCP-15 Conditional OpenClaw alpha importer:** see
  [`openclaw_research.md`](openclaw_research.md). Prefer
  `openclaw models status --json` as Tier 1; Tier 2 is a narrow, JSON5-aware,
  fail-closed scanner. Never use `--probe`, invoke a shell, mutate OpenClaw
  config, or persist a partial Anticharon shortlist. The supported OpenClaw
  version(s), observed output schema, selected-agent behavior, and first
  acceptance fixture remain `OPEN` until verified. Ship only as alpha if
  that evidence and PO acceptance case are established within this sprint;
  otherwise park the importer without expanding scope.
- **MCP-13 Parity tools** (A-6, A-7): `self_test` wraps `tester.py`'s JSON
  diagnostic (same checks as `anticharon test`, output via WS-A2A
  `messages` plus per-check data); `list_models` wraps `manager.list_models`
  (entries with `source` and `canonical_slug`). Both annotated (MCP-9).
- **MCP-14 Fallback-aware alerts** (D-5): alongside `BEST_OPTION_CHANGED`,
  emit a price alert describing the **next fallback** relative to the
  default (e.g. "your next fallback `B` is 40% more / 15% less expensive
  than default `A`"), so the cost of a failover is visible before it
  happens. Exact alert type/thresholds confirmed after E-5.

### WS-DOC — Documentation & Discoverability

- **DOC-1 Resource & spec truth pass**: single repo-root `llms.txt` shipped
  into the wheel (D-7; `src/anticharon/llms.txt` deleted; `force-include`
  in `pyproject.toml`), regenerated with current version, MCP-first usage,
  every tool/resource/prompt, the `messages` contract and §3d code catalog.
  Fix spec §5 (three files, D-22), §6 (shortlist entry shape, D-15/D-5),
  §7 (CLI commands, D-19), §10 (tools, annotations, matching rule,
  `force` replacing `force_refresh`, no `--zdr` on `check`) and BACKLOG
  Milestone 3 drift (F-9). Perform a human-reviewed version-string inventory;
  the optional helper is advisory only and its generated report remains in
  `.local/` (DOC-9).
- **DOC-2 Prompt hardening**: prompts reference MCP tools (`add_model`,
  `check_prices`) instead of CLI/Hermes commands where an MCP path exists
  (F-13); add the explicit instruction "call `check_prices` (or re-read
  `anticharon://llms.txt`) before trusting a remembered default model".
- **DOC-3 MCP installation docs** (README + `llms.txt` + spec): per-host
  snippets for the **supported** install modes only — persistent
  `uv tool install git+…` (binary at `~/.local/bin/anticharon`, written with
  `~`/`$HOME`, never a personal path — DOC-3a) and `pip install git+…`;
  source checkout (`uv run --directory`) stays documented for contributors.
  **All `uvx` snippets are removed** (README ×3, `llms.txt` ×2, spec ×2) and
  `uvx` is not mentioned as a supported mode (D-27). Each mode states how it
  receives updates (`check_updates` / `run_update`).
- **DOC-3a Home-path privacy in host configs** (PO evidence, 2026-09-24):
  `hermes mcp add anticharon --command "~/.local/bin/anticharon" --args "mcp"`
  works — Hermes expands `~`, so docs never need a personal home path
  (Rule 12). Whether each other host (Claude Desktop, Cursor, Antigravity)
  expands `~` in its config is checked in E-2 and documented per host.
- **DOC-4 Divergence item**: close the pre-plan bug as already fixed (F-10) by
  adding a parity regression test (CLI vs `--json` report the same divergence
  state); order-sensitivity handled per D-5.
- **DOC-5 Agent skill** `.agents/skills/anticharon/SKILL.md` (D-8): thin,
  for agents installing/configuring Anticharon for a user — quick-install
  CTA per install mode, host config pointer, then "read
  `anticharon://llms.txt`"; links, never copies.
- **DOC-6 Pre-work cleanup** (PO, round 1): move
  `docs/specs/pre-work/draft_eval_harness.md` to the git-ignored `.local/`
  scratchpad and remove the now-empty `docs/specs/pre-work/` folder
  (`git rm` of the tracked file after the local copy is verified).
  Update the one live reference in `docs/BACKLOG.md` (eval harness item) to
  describe the draft without linking a private path (Rule 12); the historical
  `CHANGELOG.md` mention stays as-is. §4 user stories reviewed before the
  move (result: CAND-5, CAND-6).
- **DOC-7 Beta declaration** (D-20; PO, 2026-09-24): state Beta status and
  what it means (interfaces may change without deprecation until real users
  / third-party feedback exist) in `README.md` (title area + a short
  "Status" note), `llms.txt`, the `0.6.0` CHANGELOG entry, the `.local/`
  release notes draft, and `pyproject.toml` classifier
  `Development Status :: 4 - Beta` (no classifiers exist today).
- **DOC-8 Protocol baseline governance** (§3c): add the pinned MCP spec
  version/URL to spec §10 (replacing the stale `mcp>=1.3.0 (FastMCP)` line,
  F-7), and add a short standing rule to `AGENTS.md` (Rule 4, planning
  stage): each sprint ledger records the protocol baseline and the result
  of the protocol-update check; PR descriptions cite the baseline.
- **DOC-9 Version-string inventory (supporting, not a release gate):** review
  version-like strings in user-facing documentation/discovery surfaces and
  record dispositions for flagged current-version claims.
  `scripts/supplemental_version_inventory.py` is an optional advisory helper;
  it does not decide removals or run in CI. Its generated report stays under
  `.local/`; the PO reviews the findings and records confirmed stale claims
  or exceptions in the ledger before release.

### WS-SELFUP — Self-Update Infrastructure (user-initiated, experimental)

Goal this sprint (PO, 2026-09-24): **start the self-update infrastructure**
with two user/agent-initiated operations; no background or automatic checks
(parked for the next planning round, after real-world testing). Evidence
gates E-2/E-3 now validate each update type instead of choosing a scope.

- **SELFUP-0 Evidence spike** — runs E-1…E-4 (§4) per install mode and per
  host, against the SELFUP-2 types; results recorded in §4 before release.
- **SELFUP-1 `check_updates`** — MCP tool `check_updates`, CLI
  `anticharon check-updates` (parity). Compares the **installed** version
  (`anticharon.__version__`, kept equal to `pyproject.toml` by Rule 11 — the
  wheel does not ship `pyproject.toml`) with the latest version retrieved
  from GitHub (`releases/latest`, E-4), ~2 s hard timeout (Rule 10). Returns
  JSON with boolean `is_latest` (D-26) plus details
  in the universal `messages` (`UP_TO_DATE` / `UPDATE_AVAILABLE` with the
  `run_update` action; `UPDATE_CHECK_FAILED` + `isError: true` on network
  failure). User-initiated only: no cache file, no background thread, no
  injection into other responses this sprint.
- **SELFUP-2 `run_update`** — MCP tool `run_update`, CLI
  `anticharon update --type N` (parity). Every call returns a prominent
  `EXPERIMENTAL` warning message: "experimental feature, may require manual
  intervention (e.g. `hermes gateway restart`)". Update types (PO design;
  refinements in D-9):

  | Type | Name (PO) | Sequence |
  |---|---|---|
  | 1 | update only | reinstall, then wait (host keeps running the old process until it restarts) |
  | 2 | host restart | reinstall, then `hermes gateway restart` |
  | 3 | assassin phoenix | reinstall, then kill the running `anticharon` process so the host respawns it |
  | 4 | inverted assassin phoenix | kill first, then reinstall |
  | 5 | reload request | reinstall, then ask the user to send `/reload-mcp` in chat (Hermes shows a confirm prompt warning that reload invalidates the provider prompt cache — next message re-sends full input tokens) |

  Reinstall command: `uv tool install --force git+https://github.com/parisneto/anticharon.git`;
  fallback when `uv` is not found: `<running interpreter> -m pip install --force-reinstall git+https://github.com/parisneto/anticharon.git`
  (`sys.executable -m pip`, never a bare `pip` from `PATH`; D-9).
  Types are exposed **by name** (`install_only`, `restart_host`,
  `phoenix`, `phoenix_inverted`, `reload_request`; CLI also accepts 1–5),
  visible as an enum in the MCP tool schema, in the tool docstring and in
  CLI `--help`. **The final set of types and their exact mechanics
  (process self-termination, host restart, detached execution) are chosen
  during development from PO live tests** — not fixed in planning. Process
  paths in examples and code use `~`/`$HOME` or self-discovery, never a
  personal home path (note: a quoted `"~/…"` argument is not expanded by the
  shell — e.g. `pkill -f "~/.local/bin/anticharon"` would not match; use
  `$HOME/…` or the running binary's resolved path). Annotations: `run_update`
  readOnly false, destructive true, idempotent false, openWorld true;
  `check_updates` readOnly true, openWorld true.

---

## 3a. CLI ↔ MCP Parity Matrix (D-19, D-20)

Signed off by the PO (D-21). "Local" = no network.

| Capability | CLI | MCP | Data / network |
|---|---|---|---|
| Latest normalized price + persisted alerts (display) | `check [--model]` | `check_prices(model_id?)` | `history.csv` + `alerts.json`, local; no `--zdr` (D-28) |
| 30-day history + analytics / profiles | `history [--model] [--csv]` | `get_model_history(model_id?, format)` | `effective_prices.json`, local |
| Update from source and persist | `run [--model] [--dry-run] [--force] [--zdr]` | `run_prices(model_id?, dry_run=false, force=false, zdr_only?)` *(new; today's fetch-and-write behavior of `check_prices` moves here)* | OpenRouter, writes |
| Catalog search | `model discover` | `discover_models` | OpenRouter |
| Add / remove / list shortlist | `model add` / `remove` / `list` | `add_model` / `remove_model` / `list_models` *(all new)*; resource `anticharon://shortlist.json` kept | local (+ catalog check on add) |
| Hermes import | `model sync` / `import-hermes` | `import_hermes_models` | local |
| OpenClaw import (conditional alpha) | `model import-openclaw` | `import_openclaw_models` | local OpenClaw CLI/config |
| Calibrate weights | `calibrate <csv>` | `calibrate_token_weights` | local |
| Fast calibration | proposed `calibrate-fast` | `calibrate_fast` | local |
| Self-test | `test` | `self_test` *(new)* | local + network |
| Agent briefing | `info` | resource `anticharon://llms.txt` | local |
| Version | `--version` | `serverInfo.version` | local |
| Check for updates | `check-updates` | `check_updates` | GitHub |
| Run update (experimental) | `update --type N` | `run_update(type)` | GitHub + subprocess |

Asymmetry register (each signed off by the PO; each documented in spec
§7/§10, the tool docstring, `llms.txt` and README):

| ID | Asymmetry | Reason | Status |
|---|---|---|---|
| A-1 | MCP cannot upload CSV bytes for `calibrate_token_weights` | The tool takes a server-local CSV path; if the file is not accessible to the MCP host, use `calibrate_fast` with three derived weights or the CLI | **Signed off (PO, 2026-09-24)** |
| ~~A-2~~ | ~~Prompts exist only in MCP~~ | **Rejected (PO, 2026-09-24):** prompts are business-case user guides → full parity, exposed on CLI (MCP-12) | Withdrawn |
| A-3 | `--json` / `--hints` only in CLI | MCP responses are always JSON with `_hints` | **Signed off (PO, 2026-09-24)** — spec'd asymmetry |
| A-4 | Per-call path/runtime overrides (`--config`, `--data-dir`, `--no-hermes`, `--timeout`) exist only in CLI | KISS/DRY: MCP gets them once at server launch via env (`ANTICHARON_CONFIG`, `ANTICHARON_DATA_DIR`, `HERMES_CONFIG`, `HERMES_HOME`). **The only per-call override on MCP is `import_hermes_models(hermes_config_path)`** (read-only on the source; matches CLI `model sync --hermes-config`, so that pair is at parity). If import/sync cannot solve a case, the agent is instructed (docstring, `llms.txt`, `NO_EXACT_MATCH`/import messages) to use `add_model` instead. Multi-subagent / nested setups (e.g. early OpenClaw adoption managing several configs) are out of scope — not supported, tested, or optimized this sprint | **Signed off (PO, 2026-09-24)** |
| A-5 | `help` / `mcp` commands only in CLI | MCP lists tools natively; `mcp` launches the server. The semantic map for agents is `llms.txt` (`help` ≙ `anticharon://llms.txt` / `info`) | **Signed off (PO, 2026-09-24)** — spec'd asymmetry |
| A-8 | Naming: MCP tools carry a `_prices` / `_model(s)` suffix (`check_prices`, `run_prices`, `add_model`); CLI commands do not (`check`, `run`, `model add`) | MCP tool names share a flat global namespace across servers in a host, so they need the domain noun; CLI is already namespaced by `anticharon` | **Signed off (PO, 2026-09-24)** |
| ~~A-6~~ | ~~`test` has no MCP tool~~ | **Resolved (PO, 2026-09-24):** new `self_test` tool at parity with `anticharon test` (MCP-13) | Withdrawn |
| ~~A-7~~ | ~~`model list` only as resource~~ | **Resolved (PO, 2026-09-24):** new `list_models` tool at parity with `model list`, for interface consistency even where output matches the `anticharon://shortlist.json` resource (MCP-13) | Withdrawn |

## 3b. MCP Tool Annotations — Adopted (D-23)

Source: MCP blog "Tool Annotations as Risk Vocabulary" (2026-03-16); the
`ToolAnnotations` interface shipped in spec revision `2025-03-26` with five
fields: `title`, `readOnlyHint` (default false), `destructiveHint`
(default true), `idempotentHint` (default false), `openWorldHint`
(default true). All are untrusted hints, never guarantees.

| ID | Adoption | Why | Sprint? |
|---|---|---|---|
| ANN-1 | Declare **all five** fields (including `title`) on every tool (MCP-9 extended) | Un-annotated tools get worst-case defaults; `title` improves host UX and is useful even from untrusted servers | Yes |
| ANN-2 | Values reflect **actual worst-case behavior**, reviewed against code, spec §10 and D-19; parity test fails on a missing annotation | Blog's server-author guidance; hints that lie are worse than none | Yes |
| ANN-3 | `_meta` is used only for Anticharon-specific metadata under a namespaced key (e.g. `io.github.parisneto/…`), **never as the agent-facing channel** — that is `messages` (WS-A2A) | Blog: off-the-shelf clients do not read unfamiliar `_meta` keys; corroborates D-1 and is an input to E-1 | Yes (spec rule) |
| ANN-4 | Document the session-risk profile ("lethal trifecta") in spec §10: which tools are open-world, that catalog text returned by `discover_models` (model `description`) is **untrusted third-party content**, and that `run_update` is the only tool that executes a command — input to D-9 | Blog: risk is a property of the session; tool combinations matter | Yes (docs + D-9 input) |
| ANN-5 | Draft SEPs (#1913 trust/sensitivity, #1984 governance/UX, #1561 `unsafeOutputHint`, #1560 `secretHint`, #1487 `trustedHint`) | Evidence (2026-09-24): **4 of 5 are closed** on `modelcontextprotocol/modelcontextprotocol` (#1984, #1561 dormant, #1560, #1487); only **#1913 is open, labeled `draft`**. The installed SDK (`mcp` 2.2.0) **silently drops** unknown annotation fields (`ToolAnnotations(secretHint=True)` serializes to nothing). The blog's own guidance for unmerged concepts is namespaced `_meta`, not `ToolAnnotations`. | **Verified 2026-09-24:** the latest published spec schema (`schema/2026-07-28/schema.ts`) and `schema/draft/schema.ts` in `modelcontextprotocol/modelcontextprotocol` define `ToolAnnotations` with exactly five fields — `title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` — and no SEP-derived field. **Decided (PO, 2026-09-24): track, don't ship** — standard hints now; drafts only once they enter the spec or otherwise stabilize. Annotations are hints, not security guarantees, which argues against speculative trust/security metadata. |

## 3c. Protocol Baseline & Standing Rules (PO, 2026-09-24)

- **Pinned baseline:** MCP specification `2026-07-28`
  (https://modelcontextprotocol.io/specification/2026-07-28). Every
  protocol-shaped decision in this sprint (annotations, error signaling,
  `_meta`, tool naming) cites it.
- **Standing standard (this sprint and forward) — error signaling:**
  detailed, agent-readable explanation goes in the universal `messages`
  array (WS-A2A); failure is signaled with the spec-standard
  `isError: true` tool result for the widest host compatibility (spec
  `server/tools` → Error Handling). CLI equivalent: non-zero exit code.
- **Citation rule:** the spec version and URL are recorded in
  `docs/specs/spec_v1_anticharon.md` §10, in this ledger, and in the sprint
  PR description.
- **Protocol-update check (every future sprint):** sprint planning starts by
  checking for new MCP specification revisions (and relevant agent-to-agent
  protocol changes) since the pinned baseline; any change is recorded as a
  finding in that sprint's ledger before scope is closed. Codified in
  `AGENTS.md` by DOC-8.

## 3d. Agent Message Contract — Catalog (D-1, approved)

Message object: `level` (`info` | `warning` | `error`), `code` (stable
string), `text` (one human sentence), optional `action`
(`{"mcp": "<tool call>", "cli": "<command>"}`), optional `model` (slug, for
per-model messages). Top-level response keys: `status`, `messages`
(never empty, D-1b), `elapsed_ms`, then the payload.

`status` values: `success` · `warning` (done, with per-item problems) ·
`error` · `refused` · `not_monitored`. **`isError: true` (MCP) / exit code 1
(CLI) iff `status` ∈ {`error`, `refused`}** — the requested operation was
not performed (§3c). `warning` and `not_monitored` are normal results;
`not_monitored` is used only by local reads. A filtered live run whose exact target is absent from the shortlist is
`refused` and sets MCP `isError: true`; it does not query the catalog or fetch
prices for that target.

| Code | Level | Emitted by | Meaning / `action` |
|---|---|---|---|
| `COMPLETED` | info | every command/tool | "Anticharon processed your request successfully in 0.4s" |
| `DATA_STALE` | warning | `check`, `history` | latest local observation older than today → `run` / `run_prices` |
| `PREVIEW_ONLY` | info | any `dry_run` | full work done, nothing persisted → rerun without `dry_run` |
| `SHORTLIST_UPDATED` / `SHORTLIST_UNCHANGED` | info | `run`, sync/import, add/remove, calibrate | what was persisted |
| `NO_DEFAULT` | info | `check`, `history`, `run` | no default set (D-24) → `import_hermes_models` / `add_model(default=true)` |
| `NOT_MONITORED` | warning on local reads; error/refused on filtered live run | `check`, `history`, `run --model` | exact target is absent from the Anticharon shortlist. Local reads make no network call; `run --model` refuses without catalog lookup or price fetch → `add_model` (which validates) |
| `NO_EXACT_MATCH` | warning per model in full `run`; error/refused on `add_model` | catalog-backed exact-match operations only | catalog has no exact slug → `discover_models`; never emitted by local reads, `run --model`, or `remove_model` |
| `PRICE_UNAVAILABLE` / `PRICE_INVALID` | warning | `run` (per model) | model skipped, reason stated (F-15) |
| `API_FALLBACK` | warning | `run` | OpenRouter unreachable, cached history used (existing `api_offline_fallback`) |
| `CATALOG_UNAVAILABLE` | error | `add_model` | catalog unreachable; external cause stated; not persisted → retry later (D-12) |
| `SOURCE_MANAGED` | error (`refused`) | `remove_model`, `add_model(default=true)` | entry/default owned by Hermes → change it there (D-13, D-25) |
| `HERMES_INCOMPLETE` | warning | `run`, `check`, `test`, sync/import | partial detection; shortlist protected (spec §6.2) |
| `HERMES_DIVERGENT` | warning | `run`, `check`, `test` | Hermes sequence ≠ Hermes-sourced entries (D-5) → `import_hermes_models` |
| `HERMES_NOT_DETECTED` | warning | `run`, `check`, `history`, sync/import | no Hermes configuration found; standalone operation stays successful (never an error) → pass a Hermes config path / `$HERMES_CONFIG`, or `--no-hermes` (D-1e) |
| `CALIBRATION_INPUT_INVALID` | error | `calibrate` | activity CSV missing, unreadable or not parseable; `status: "error"`, CLI exit 1 / MCP `isError: true`, full JSON envelope under `--json`; nothing persisted → re-export the log (D-1e) |
| `ZDR_LIVE_LIMITED` | warning | `model discover --zdr` | live ZDR results are limited: the check was capped at `max_zdr_check_count` (states how many of how many candidates were checked) and/or compliance is unknown for named models (kept routable-by-default); replaces the ad-hoc `zdr_warning` key (D-1e) |
| `CALIBRATION_BACKUP` | info | `calibrate` | previous weights saved; path given (D-17) |
| `SELF_TEST_FAILED` | error | `test` / `self_test` | one or more checks failed; per-check `error` in payload |
| `UP_TO_DATE` / `UPDATE_AVAILABLE` | info | `check_updates` | installed vs latest; → `run_update` |
| `UPDATE_CHECK_FAILED` | error | `check_updates` | network/API failure, cause stated |
| `EXPERIMENTAL` | warning | `run_update` | always; may need manual intervention |
| `UPDATE_INSTALLED` / `UPDATE_FAILED` | info / error | `run_update` | outcome of the reinstall step |
| `RESTART_REQUIRED` | warning | `run_update` (types 1, 5) | new version active only after restart / `/reload-mcp` |

Retired proposals (superseded in grilling): `AMBIGUOUS_MODEL` (D-14),
`HERMES_OVERRIDES_SHORTLIST` (D-2), `CANONICAL_CHANGED` (D-16),
`MODEL_RESOLVED_BY_PREFIX` (D-14), `CATALOG_UNVERIFIED` (D-12),
`action_required` level (folded into `warning` + `action`).

### 3e. Initial ICP and use-case ledger (KISS scope)

**Working ICP:** a developer/operator using OpenRouter through an agent or
orchestrator who needs dependable model pricing, an explicit shortlist,
recent history, and token-weight calibration. This is a narrow starting
hypothesis, not a broad market/persona taxonomy.

| Use case | Need captured in this sprint | Parked work |
|---|---|---|
| New or cold-start model | Show current price when available; distinguish missing history from missing pricing and avoid unsupported maturity claims. | Evaluation harness and maturity scoring |
| Dynamic model aliases | Do not silently replace a requested slug; explain exact-match/discovery behavior. | Alias lifecycle analysis and automatic alias-risk scoring |
| Provider resilience | Capture multi-provider/fallback awareness in model-management use cases. | Provider liquidity evaluation and routing optimization |
| Maintainer CI stress evaluation | Preserve the need discovered in eval-harness stories. | Eval harness, prompts, metrics, and CI gate |

The source draft `draft_eval_harness.md` remains private under `.local/` per
DOC-6; its implementation is not part of this sprint.

### 3f. Calibration input and validation

The three weights are finite numeric shares in `[0, 1]`:
`weight_uncached_prompt`, `weight_cached_prompt`, and `weight_completion`.
They must sum to `1.0` within `0.000001`, matching persisted precision;
within that tolerance, normalize by the sum and round to six decimals before
persisting. Reject booleans, strings, NaN, infinity, out-of-range values, or
a total outside tolerance with a useful message. For log-derived calibration,
token counts must be non-negative integers and total tokens must be greater
than zero; zero completion tokens are valid. **Resolved for W4 (2026-09-25):**
the W4 task directive confirms the `0.000001` tolerance and requires
normalization within that tolerance, rounded to six decimals before saving.

The MCP calibration-details resource explains the three components, includes
sample OpenRouter log lines and derivation guidance for an agent to provide
the resulting weights to `calibrate_fast`, and offers the CLI CSV workflow
as the user-approved fallback. `calibrate_token_weights` accepts a
server-local CSV path; full CSV content is not sent over MCP (A-1).

## 4. Evidence Gates (run before dependent code)

| ID | Question | Method | Decides |
|---|---|---|---|
| E-1 | Do target hosts (Claude Desktop, Hermes, Cursor, MCP Inspector) show MCP `_meta` and server `instructions` to the model, or only in-band payload keys? | Run each host against a build that emits a sentinel in `_meta`, `instructions`, and `messages`; ask the model what it sees; record observations and outcome in this ledger | MCP-4 (`instructions` reach), ANN-3 confirmation |
| E-2 | Per supported install mode — `uv tool install git+…`, `pip install git+…`, `uv run --directory` (source); `uvx` excluded (D-27) — how does a user actually get a new version, and can the running process detect which mode it is in? | Scripted install of `v0.5.5` then a local newer tag in each mode; record the upgrade command, whether `uv tool upgrade anticharon` re-resolves the git ref, and `sys.executable`/`sys.prefix` markers | DOC-3, SELFUP-2 `action`, D-9 |
| E-3 | After the server process exits (code 0 and non-zero), does each host respawn the stdio server automatically, on next tool call, or never? | Tool that exits; observe each host | D-9 |
| E-4 | Is `releases/latest` a reliable version source (Release-vs-tag gaps, e.g. `v0.5.4`), and what are the unauthenticated rate-limit and failure modes? | API calls + recorded fixtures under `tests/fixtures/` | SELFUP-1 |
| E-5 | Does displaying the shortlist in **Hermes fallback order** (default → fallback 1 → …) instead of price order make failover cost clearer, and in which surfaces (`check` table, TUI chart, JSON order)? | Prototype both orders with real shortlist data during the sprint; record observations and PO decision in this ledger before MCP-14 / display changes merge | MCP-14, display order |

Evidence findings and any necessary sample payloads are recorded here with
local paths stripped (Rule 4 / Rule 12). Screenshots are not required.

### W5 evidence record — 2026-09-26

- **E-1 — pending PO host verification.** This implementation workspace has
  no configured Claude Desktop, Hermes, Cursor, or MCP Inspector target. The
  required sentinel/model observation therefore cannot be truthfully recorded
  here. Verify all four hosts before release; do not infer model visibility
  from MCP server metadata alone.
- **E-2 — pending PO install-matrix verification.** The requested three-mode
  install/upgrade experiment needs disposable user installations and a local
  newer tag. It was not run against an operator installation. The shipped
  fallback is deterministic: if `uv` is unavailable, updates invoke
  `sys.executable -m pip`, and `uvx` remains unsupported (D-27).
- **E-3 — pending PO host-respawn verification.** No target MCP host is
  connected to this workspace, so stdio respawn behavior after process exit
  is not observable. The experimental Phoenix sequences surface a restart
  requirement and must be exercised only in the host matrix.
- **E-4 — passed implementation/API evidence.** On 2026-09-26, GitHub
  `repos/parisneto/anticharon/releases/latest` returned HTTP 200 with
  `tag_name: v0.5.5` and an unauthenticated-compatible rate-limit response
  header set. The recorded response is
  `tests/fixtures/github_releases_latest.json`; deterministic tests cover
  equal-version, timeout/error, and MCP `isError` behavior. The endpoint is
  an appropriate current-version source;
  release-vs-tag gaps remain an acknowledged limitation of `releases/latest`.
- **MCP-15 — parked.** OpenClaw's supported version, observed
  `models status --json` schema, selected-agent behavior, and first
  acceptance fixture remain OPEN. No importer or parser was shipped, rather
  than guessing at a partial shortlist write.

### W6 evidence record — 2026-09-26

- **E-5 — implementation prototype observation.** Price order remains the
  clearest general comparison for the `check` table, TUI spectrum, and JSON
  list: it identifies the least-cost model without implying Hermes will select
  it on failover. Hermes order is essential only for the failover question,
  because the immediate fallback can differ from the least-cost model. W6
  therefore leaves those existing price-ordered surfaces unchanged and adds a
  persisted `NEXT_FALLBACK_PRICE` alert that explicitly compares the default
  with Hermes `order: 1`. Its deterministic fixture covers an unpriceable
  immediate fallback with `NEXT_FALLBACK_UNAVAILABLE`, rather than silently
  selecting a later fallback. The alert has no threshold: its role is to show
  the known cost of the next failover, including a lower-cost fallback.

---

## 5. Decision Register

| ID | Decision | Status | Resolution |
|---|---|---|---|
| D-1 | `AgentMessage` schema, `status` values, `isError` mapping, code catalog | **DECIDED (PO, 2026-09-24)** | As §3d |
| D-1b | `messages` presence | **DECIDED (PO, 2026-09-24)** | Always present and **never empty**: every response carries at least a completion message (e.g. `COMPLETED`, `info`: "Anticharon processed your request successfully in 0.4s", with elapsed time measured per command/tool call). Errors and warnings are added alongside it. |
| D-1c | Legacy communication keys | **DECIDED (PO, 2026-09-24)** — clean break, no mirroring (zero known external users) | (1) `notice`, `hint`, top-level `message`, `hermes_integration.warning` / `model sync` `warning`, and top-level `error` are folded into `messages` (`hint` → `action`) and removed; (2) `status` stays as the single machine outcome word; (3) `priceWarnings[].message` stays (alert data), and `priceWarnings` is renamed `price_warnings` (A2A-8, ex-CAND-3); (4) per-check `error` fields in `anticharon test` stay as diagnostic data, with overall failure also emitted as a message. Tests asserting on removed keys migrate to asserting message `code`s (disclosed per Rule 8). |
| D-1e | Codes for conditions the §3d catalog did not cover (W1 design gap) | **DECIDED (PO, 2026-09-25)** — additive catalog entries | (1) Hermes configuration not found → `HERMES_NOT_DETECTED`, `warning`, short explanation plus action; standalone operation stays successful and the absence of the optional Hermes config is never an error (CLI `model sync` therefore returns `status: "warning"`, exit 0, like MCP `import_hermes_models`). (2) `calibrate` activity-CSV parse/read failure → `CALIBRATION_INPUT_INVALID`, `error`, safe actionable text, `status: "error"`, CLI nonzero / MCP `isError: true`, full JSON envelope under `--json` (never stderr-only). Only invalid/unreadable input maps to this code; the existing error model has no internal-failure code, so any other exception is not reported as invalid input. (3) `model discover --zdr` cap notice → `ZDR_LIVE_LIMITED`, `warning`, keeping the "live ZDR results are limited" explanation; the parallel `zdr_warning` key is removed. |
| D-1d | `_hints` field glossary in payloads | **DECIDED (PO, 2026-09-24)** — kept as-is | Not a communication key (it is an in-band field glossary). Verified it is **not** the MCP spec's tool-annotation "hints" (`readOnlyHint` etc., declared on tool *definitions*, not in results) — those are adopted separately as MCP-9. `_hints` is an Anticharon convention, neither required nor discouraged by the spec. |
| D-2 | Shortlist authority across writers | **DECIDED (PO, 2026-09-23)** | Models added by an agent/user are persisted independently of Hermes sync and any future integration, survive every sync conflict, and stay until explicitly removed. Entries are type-identifiable in JSON (`source` key) and distinguishable in the TUI. Implemented by MCP-7. |
| D-3 | `force_refresh` | **RESOLVED by D-19** (agent proposal, PO may override) | Removed. Its only effect was a longer timeout; with `run` respecting the same-day cache rule, the meaningful switch is `force` (refresh even if already updated today) on both CLI (`run --force`) and MCP. |
| D-4 | `get_model_history` network behavior | **RESOLVED by D-19** | Local read only (matches its own description). Annotation becomes `readOnlyHint: true`, `openWorldHint: false`. |
| D-4b | Multi-hit substring behavior in `get_model_history` | **RESOLVED by D-14 / D-19** | Exact match only and local-only: exact slug in shortlist → history; absent from shortlist → `status: not_monitored` + `NOT_MONITORED` (action `add_model`, which validates against the catalog). It never queries the catalog or emits `NO_EXACT_MATCH`. `AMBIGUOUS_MODEL` code dropped. |
| D-5 | Hermes order & divergence | **DECIDED (PO, 2026-09-24)** | **Order matters.** Hermes resolves `fallback_providers` strictly sequentially (top to bottom) on failover triggers (HTTP 429/quota, 5xx/outages, network drops, 401/403 after credential pools, client-initialization errors). Therefore: (1) Hermes-sourced entries persist their **source order** in an explicit order key on the D-15 entry object (e.g. `order`: 0 = Hermes default, 1…n = fallbacks); (2) the divergence check compares the Hermes sequence **order-sensitively** against Hermes-sourced entries only (manual entries never count, D-2) — the current order-sensitive compare in `tester.py` is correct in principle, only its scope changes; (3) enhancement MCP-14 (fallback-aware alerts) and spike E-5 (fallback-order display). Context note: prompt-cache hit rate after a switch depends mainly on the provider's minimum prompt length (≥ 1,024 tokens), not on elapsed time — hits resume on the next turn — so cache warm-up is not a factor in model-switch advice. |
| F-19 fix | Default model identification | **DECIDED (PO, 2026-09-24)** | No dedicated `default` key. The default is the Hermes-sourced entry at source position 0 (`order` 0), valid because import/sync preserve source order and entries are typed `hermes` (D-15). Documented in spec §6.2. Manual entries are never implicitly the default (fixes F-19). Display and alerts when **no** default exists: D-24; explicit default for non-Hermes users: D-25. |
| D-6 | `calibrate_token_weights` input | **RESOLVED (PO, 2026-09-24)** | The MCP tool accepts a server-local CSV path and uses the CLI calculation; CSV bytes are not uploaded through MCP. If the log is not accessible to the server, `calibrate_fast` accepts the three host-derived weights, with derivation and CLI fallback documented in the resource. Recorded as transport asymmetry A-1 (§3a). |
| D-7 | `llms.txt` location | **DECIDED (PO, 2026-09-24): Option 1** — single repo-root `llms.txt`, shipped into the wheel via `[tool.hatch.build.targets.wheel.force-include]` `"llms.txt" = "anticharon/llms.txt"`; `src/anticharon/llms.txt` deleted. CI builds the wheel and asserts `anticharon/llms.txt` is inside (kept out of the fast pytest gate). | Evidence 2026-09-24: `uv build --wheel` (hatchling, `packages = ["src/anticharon"]`) ships **only** `src/anticharon/**` — the repo-root `llms.txt` is **not** installed by `uv tool install` / `pip install` / `uvx --from git+…`. Option 1 (single root file) therefore needs `[tool.hatch.build.targets.wheel.force-include]` mapping `llms.txt` → `anticharon/llms.txt`; `resource_llms_txt()` already falls back to the repo root when running from source. Option 2: keep both copies, enforced by an `AGENTS.md` rule + acceptance test. |
| D-8 | Agent skill audience | **DECIDED (PO, 2026-09-24)** | Agents that install and configure Anticharon for a user (adoption first: remove barriers, like `llms.txt` and prompts). **Thin** `.agents/skills/anticharon/SKILL.md`: a quick-install CTA (one command per install mode + host config snippet pointer), then "in MCP mode, read `anticharon://llms.txt`" — links to `llms.txt`/README, never copies them. Contributor rules stay in `AGENTS.md`. Multiple agent-facing doc surfaces now exist (`llms.txt`, prompts, skill, README, tool descriptions); a future **docs release gate** is noted as a candidate (CAND-9). |
| D-9 | Self-update scope | **DECIDED (PO, 2026-09-24)** | Start infrastructure: `check_updates` + `run_update` (SELFUP-1/2), experimental. Round-17 refinements: **named types** — approved (enum visible in schema/docstring/`--help`); **pip targets the running interpreter** (`sys.executable -m pip`) — approved, live-tested by the PO (not by agents); **type mechanics / final candidates** (self-kill via detached process, host restart safety) — decided during development from PO live tests; **install-mode guard** — not adopted: `uvx` is simply unsupported (D-27). |
| D-9b | Version check trigger | **DECIDED (PO, 2026-09-24)** | User-initiated only (`check_updates`) this sprint. Background/cached/automatic checks and in-band `UPDATE_AVAILABLE` on other responses are **parked** for the next planning round after real-world testing. |
| D-10 | Release version | **RESOLVED (PO, 2026-09-24)** | `0.6.0`, declared **Beta** — a `1.0.0` would contradict the Beta declaration and Rule 11's "production-proven" bar. |
| D-11 | Promote the private input documents | **DECIDED (PO, 2026-09-24)** — no | Fully incorporated into the ledger; promoting them would be bloat. |
| D-12 | `add_model` when the catalog cannot be reached/confirmed | **DECIDED (PO, 2026-09-24)** | Do **not** persist. Return an error with a `CATALOG_UNAVAILABLE` message that clearly states the external problem (e.g. OpenRouter timeout / HTTP status) and the action "retry later". No unverified adds. |
| D-13 | `remove_model` on a non-`manual` entry (`hermes`, future `import:<name>`) | **DECIDED (PO, 2026-09-24)** | Refused by policy (the entry would reappear on next sync). Response carries `status: "refused"` and a `SOURCE_MANAGED` message explaining why, naming the owning source and suggesting removal there (for Hermes: the exact config location / command). Anticharon never writes to the source. |
| D-14 | Slug matching policy (F-16) | **DECIDED (PO, clarified 2026-09-25)** | Exact matching only; never substitute a prefix/similar slug. Local `check` / `history` compare only with shortlist entries and report `NOT_MONITORED` if absent; they do not query the catalog. `run --model X` is an exact filter over the configured shortlist: if X is absent, refuse with `NOT_MONITORED` / MCP `isError: true` / CLI nonzero exit and do not query the catalog or fetch prices. `add_model` validates exact catalog identity before writing; a missing exact catalog slug is `NO_EXACT_MATCH`, while catalog failure is `CATALOG_UNAVAILABLE`. `remove_model` matches the exact stored shortlist key and performs no catalog lookup, so stale/invalid entries remain removable. Fuzzy matching is limited to discovery/filter operations. The model's `canonical_slug` remains surfaced as specified in MCP-8; no prefix fallback. |
| D-15 | `shortlist.json` shape for sources | **DECIDED (PO, 2026-09-24)** | Entries become objects `{"model": "<slug>", "source": "manual" \| "hermes" \| "import:<name>"}`, plus `order` for Hermes sequence / manual default (D-5, D-25). Legacy flat `[str]` lists are read as `hermes` when Hermes is detected, otherwise `manual`, and rewritten in the new shape on the next write. Exact field set may grow during implementation; spec §6 updated in the same change. |
| D-16 | `canonical_slug` drift (same `id`, new dated `canonical_slug`) | **POLICY DECIDED, IMPLEMENTATION PARKED (PO, 2026-09-24)** — never observed by the PO; only related known risk is `*-latest` alias models (already a non-goal). Parked for investigation (see Deferred); this sprint only surfaces the already-stored `canonical_slug` (MCP-8). Policy if/when proven: | A new `canonical_slug` is a new model for data purposes: its data is refreshed (backfill against the new `permaslug`) and represented as that model. **No warning, no mixed-version history.** If the new canonical has no history, its profile labels change accordingly (e.g. `NEWLY_TRACKED`) — simple, direct, transparent. Price history is therefore keyed by `canonical_slug`; `id` stays the user-facing name. |
| D-17 | MCP-9 annotation values per tool | **DECIDED (PO, 2026-09-24)** | Table in MCP-9 as proposed, except both calibration tools are non-destructive because they save the previous weights to a `.bak` before writing (MCP-5). Superseded detail: `check_prices` was first kept as one read/write tool (D-18); after D-19 it is a local read (`readOnlyHint: true`) and writing moved to `run_prices`. |
| D-18 | Persist-on-observe rule for price checks | **DECIDED (PO, 2026-09-24)** | Whenever a price check obtains new prices (listed or history) for a shortlisted model (`manual` or `hermes`), they are **persisted** — including when only one model is checked. Mixed recency across the dataset is acceptable. On a full-shortlist update, the same-day rule lets execution skip models already refreshed that day. Implementation stays light. Follow-ups D-18b, D-18c decided. |
| D-18b | `dry_run` semantics vs. defaults | **DECIDED (PO, 2026-09-24)** | `dry_run` keeps one meaning everywhere: *do the full work, persist nothing*. It is a switch; its **default** is a separate choice and becomes **save** (non-conservative) on every price-fetching surface — after D-19 that is `run` / `run_prices` (`dry_run=false` default; CLI persists unless `--dry-run`). Today's CLI `check` has `--dry-run` hard-wired to `True` (`store_true, default=True`, `src/anticharon/cli.py:602`), so it can never persist — removed by this decision. |
| D-18c | Single-model live update | **DECIDED (PO, clarified 2026-09-25); surface re-mapped by D-19** | `run --model` / `run_prices(model_id)` exact-filters the configured shortlist. If present, only that shortlisted model is fetched and persisted. If absent, return `NOT_MONITORED`, refuse the request (MCP `isError: true`, CLI nonzero exit), and do not query the catalog or fetch prices. Without `--model`, update the full shortlist (same-day rule may skip refreshed entries). Never substitute a prefix match. `add_model` remains the separate catalog-validation operation and uses `NO_EXACT_MATCH` for an invalid/nonexistent slug. |
| D-19 | Command separation (surface-independent) | **DECIDED (PO, 2026-09-24)** | **`check`** = local read of the latest normalized/blended price per calibration (last price in Anticharon's memory, display only; source `history.csv`, the compact summary; no network) **including price alerts, which it reads as persisted — no recalculation** (no new data ⇒ nothing to recompute). **`history`** = local read like `check`, but over the long-term granular 30-day `effective_prices.json`; **analytics / model classification (profiles, CV%, trend, sibling alternatives) live inside `history`**, not in `check`. **`run`** = fetch from source and write **both `history.csv` and `effective_prices.json`**, respecting cache (same-day) rules, and **pre-computes the alerts at persist time** from the freshest observation plus the long-term series (`effective_prices.json` is therefore mandatory input for alerting). Today all three fetch live (`check` ≡ `run --dry-run`; `history` fetches and discards). Applies identically to CLI and MCP (D-20). |
| D-20 | CLI ↔ MCP parity | **DECIDED (PO, 2026-09-24)** | Every CLI command/argument and MCP tool/parameter is **feature-identical**. Any asymmetry must be listed in the Parity Matrix (§3a) and signed off by the PO, and documented in plan, spec, code docstrings and user docs. MCP signatures may change freely now: the project is **Beta** until real users / third-party feedback exist (DOC-7). |
| D-21 | Parity matrix sign-off | **DECIDED (PO, 2026-09-24)** except CLI prompt syntax (implementation detail, recorded when built) | `run_prices` name (A-8); A-2 withdrawn (prompt parity, MCP-12); A-3, A-4, A-5 signed off; A-6/A-7 withdrawn by adding `self_test` and `list_models` (MCP-13). Registered asymmetries: A-1, A-3, A-4, A-5, A-8. |
| D-22 | Persisted alert storage | **DECIDED (PO, 2026-09-24): Option B** | New third file **`alerts.json`** (same data dir, same path resolution as spec §6.1), written only by `run` / `run_prices`: the run's `price_warnings` list as built, plus run context (timestamp, default model, `data_source`). Alert computation is **decoupled** from the fetch/update code path so local, read-only consumers (`check`, `history` analytics) never trigger network or recalculation. **Rule 1 (approved):** `run --model X` replaces X's per-model alerts and recomputes cross-model alerts (`BEST_OPTION_CHANGED`, MCP-14 fallback alert) from the stored prices of all models; other models' alerts are kept (mixed recency, D-18). **Policy (ZDR) results are never persisted** — see D-28. Spec §5 becomes "Three Files, Three Lifecycles": `effective_prices.json` (history, source of truth), `history.csv` (compact price summary), `alerts.json` (latest alerts). |
| D-23 | Tool-annotation adoption | **DECIDED (PO, 2026-09-24)** — land all annotations | ANN-1…ANN-4 in sprint: every field of the spec's `ToolAnnotations` (all five) on every tool. ANN-5 (draft SEPs): track, don't ship (§3b). |
| D-24 | Output when no default exists | **DECIDED (PO, 2026-09-24)** | No stand-in benchmark — a default must be set. No ★ badge, no default-based alerts (`BEST_OPTION_CHANGED`, MCP-14 fallback alert), plus one `info` message `NO_DEFAULT`, e.g.: "No default model set, so alerts that compare against a default are off. Import from Hermes (`import_hermes_models`) or set one using `model add --default` or its MCP equivalent `add_model(default=true)`." |
| D-25 | Explicit default without Hermes | **DECIDED (PO, 2026-09-24)** — in scope | Users/agents set a default via CLI `model add X --default` and MCP `add_model(model_id, default=true)` (parity, no asymmetry); stored as `order: 0` on the `manual` entry; at most one manual default (setting a new one clears the old). **When Hermes is detected with a default, Hermes wins** automatically (the ICP scenario, no questions asked): a manual `--default` is refused with `SOURCE_MANAGED` and `isError: true` (the manual entry itself may still be added). Finer-grained control is parked (multi-agent item). |
| D-26 | `check_updates` boolean key name | **DECIDED (PO, 2026-09-24)** | `is_latest` (true when the installed version equals the latest release). |
| D-27 | `uvx` support | **DECIDED (PO, 2026-09-24)** — unsupported, not documented | `uvx` runs from a local cache with no real benefit beyond a pre-onboarding trial and likely persistence problems; KISS: `uvx` is not a supported mode, not recommended, and not mentioned in user docs (DOC-3 removes existing snippets). Revisit only with a real need (parked). |
| D-28 | `--zdr` on local reads | **DECIDED (PO, 2026-09-24)** — removed | ZDR is live-only: providers change dynamically and the filter narrows scope, so it must use the freshest data. `--zdr` / `zdr_only` exist only on `run` / `run_prices`; removed from `check` / `check_prices` entirely. Policy prices and `POLICY_UNROUTABLE` / `POLICY_UNKNOWN` alerts are returned in the live response only, never written to `alerts.json` or `history.csv`. |
| D-29 | Save-by-default rule for every MCP tool that writes | **DECIDED (PO, 2026-09-24)** — generalizes D-18b | **Every MCP tool that writes saves by default**, exactly like its CLI command (D-20): `run_prices`, `add_model`, `remove_model`, `import_hermes_models`, conditional `import_openclaw_models`, `calibrate_token_weights`, and `calibrate_fast`. `dry_run` exists **only** on tools that write, and only as an opt-out (`dry_run=true` / `--dry-run` = do the full work, save nothing). Read-only, local tools (`check_prices`, `get_model_history`, `list_models`, `discover_models`, `check_updates`) have no `dry_run`. This replaces the `dry_run=true` defaults found in v0.5.5 code (`import_hermes_models`) and in early ledger drafts (MCP-1, MCP-5). Unrelated and unchanged: D-13 still refuses removing a Hermes-managed entry (`SOURCE_MANAGED`); hosts may independently ask the user to confirm tools annotated `destructiveHint: true` — that is host UI, not an Anticharon refusal. |

Decided during development (by design, not open scope): the final
`run_update` type set and mechanics (PO live tests, D-9); CLI prompt syntax
(D-21); MCP-14 alert thresholds and display order (E-5, PO confirms).

---

## 6. Acceptance Criteria

### WS-A2A
- Every MCP tool and every CLI `--json` payload carries `messages` per D-1b;
  every `AgentMessage.code` is documented in `llms.txt` and spec §10.
- Human CLI output renders the same messages from the same objects (no
  duplicated message strings between JSON and CLI paths).
- In MCP mode, no message text reaches `stdout` outside JSON-RPC frames
  (ADR 0001 stdio isolation still holds).

### WS-MCP
- `add_model` / `remove_model` persist by default (`dry_run=true` opts out,
  D-29) via `manager`; D-2, D-13, D-25 rules enforced and visible in
  `messages`; refusals return `isError: true`.
- `run`/`run_prices` write `history.csv`, `effective_prices.json` and
  `alerts.json`; `check`/`check_prices` read persisted alerts without
  recalculation; ZDR results are never persisted (D-22, D-28).
- No shortlisted model is ever dropped or substituted silently (F-15,
  F-16): each skip emits a per-model message. `run --model` exact-filters the
  configured shortlist and refuses an absent slug as `NOT_MONITORED` without
  catalog or price network calls; `add_model` validates exact catalog identity
  and emits `NO_EXACT_MATCH` for a nonexistent slug (D-14, D-18c).
- The default is never inferred from list position (F-19); no default →
  `NO_DEFAULT`, no ★, no default-based alerts (D-24).
- `get_model_history` on an unshortlisted model returns
  `status: "not_monitored"` with an actionable `NOT_MONITORED` message — never
  a bare empty list.
- Tool descriptions state write side effects, network behavior, and point to
  `anticharon://llms.txt`; spec §10.2 matches each description word-for-word
  in meaning.
- MCP `initialize` reports `serverInfo.version == anticharon.__version__`.
- `calibrate_token_weights` produces weights identical to
  `anticharon calibrate` on `docs/sample/` fixtures.

### WS-DOC
- `llms.txt` version string equals `__version__`, enforced by a test.
- Every tool/resource/prompt registered on the server is listed in
  `llms.txt` and spec §10, enforced by a test that enumerates the server
  registry (prevents F-8/F-9 drift from recurring).
- README shows, per host, the supported install modes (`uv tool install`, `pip install`; no `uvx`, D-27) with `~`/`$HOME` paths and how each is updated.
- Built wheel contains `anticharon/llms.txt` from the single root file (D-7, CI check).
- Divergence parity test passes (CLI and `--json` agree).
- DOC-9 version-string inventory is human-reviewed before release; every
  flagged user-facing current-version claim has a disposition in the ledger.
  The optional inventory script is advisory, writes only to `.local/` when
  asked to save, and is not a CI gate.

### WS-SELFUP
- `check_updates` / `check-updates` never raises, respects its hard timeout,
  and makes zero network calls in the default test suite (fixtures for
  current / newer / malformed / 403 responses).
- `UPDATE_AVAILABLE` only when `latest > installed` (SemVer compare,
  pre-releases ignored); boolean key per D-26.
- `run_update` always emits the `EXPERIMENTAL` warning; subprocess
  construction for every type is unit-tested with the subprocess layer
  mocked (no real install/kill in CI); each type's real behavior is recorded
  per host/install mode in §4 (E-2/E-3) before release.

### CLI ↔ MCP parity (D-20)
- Every CLI capability has an MCP equivalent and vice versa, except the
  asymmetries in §3a, each signed off by the PO and documented in spec,
  docstrings, `llms.txt` and README; enforced by the parity test (MCP-11).
- `check`/`check_prices` and `history`/`get_model_history` make **zero**
  network calls (test patches `requests` to fail); only `run`/`run_prices`,
  `discover_models`/`model discover`, `add_model` catalog check and SELFUP
  touch the network.

### Beta status
- Beta declared in README, `llms.txt`, CHANGELOG `0.6.0`, release notes
  draft, and `pyproject.toml` classifier (DOC-7).

### Manual release gates (never automated)
- **MG-1 MCP Inspector ritual:** the PO runs `scripts/inspect_mcp.sh`
  (official MCP Inspector) against the release candidate for visibility into
  the MCP interface. Exercise each checklist item below and record pass/fail,
  a one-line note, date, and commit in this ledger. No screenshots required.

  | Kind | Item | Result | Note |
  |---|---|---|---|
  | Tool | `check_prices` | | |
  | Tool | `run_prices` | | |
  | Tool | `get_model_history` | | |
  | Tool | `discover_models` | | |
  | Tool | `add_model` | | |
  | Tool | `remove_model` | | |
  | Tool | `list_models` | | |
  | Tool | `import_hermes_models` | | |
  | Tool | `import_openclaw_models` (if shipped) | | |
  | Tool | `calibrate_token_weights` | | |
  | Tool | `calibrate_fast` | | |
  | Tool | `self_test` | | |
  | Tool | `check_updates` | | |
  | Tool | `run_update` (experimental; safe type or skipped with reason) | | |
  | Resource | `anticharon://llms.txt` | | |
  | Resource | `anticharon://history.csv` | | |
  | Resource | `anticharon://shortlist.json` | | |
  | Resource | calibration details (if shipped) | | |
  | Prompt | `cost_spike_triage` | | |
  | Prompt | `model_migration_advisor` | | |
  | Prompt | `family_upgrade_discover` | | |
  | Prompt | `daily_cost_briefing` | | |
  | Prompt | `budget_optimization_audit` | | |
- **MG-3 Hermes host test:** after the upgrade, `hermes mcp test anticharon`
  run on the PO's Hermes host; tool count and connect time recorded here.
  Baseline (v0.5.5, PO, 2026-09-24): transport stdio →
  `~/.local/bin/anticharon`, auth none, connected in 2441 ms, **4 tools
  discovered** (`check_prices`, `get_model_history`, `discover_models`,
  `import_hermes_models`). Expected after this sprint: every tool in the
  §3a parity matrix discovered (including `run_prices`, `add_model`,
  `remove_model`, `list_models`, both calibration tools, `self_test`,
  conditional `import_openclaw_models`, `check_updates`, `run_update`); any
  connect-time regression explained.
- **MG-2 Product Owner sign-off:** explicit PO approval in chat after MG-1,
  MG-3 and the automated gate pass; recorded here with date and commit. No tag or push
  to `main` before MG-2 (Rule 11).

### Release governance (Rule 11)
- Version bump across `pyproject.toml`, `src/anticharon/__init__.py`,
  `README.md`, `CHANGELOG.md`, and the root `llms.txt` in one commit.
- `docs/BACKLOG.md`: the calibrate MCP item marked complete; Milestone 3 text
  corrected; eval-harness link reworded (DOC-6); parked items from
  "Deferred" added; nothing else touched.
- Release notes draft written to `.local/`.
- GitHub issues are created before Wave 1; actual numbers are recorded in §10 and committed in one issue-registration commit before implementation.

---

## 7. Testing Strategy (Rule 8)

- **Unit**: `AgentMessage` serialization, `status` → `isError` mapping and
  CLI rendering; SemVer compare; same-day rule with an injected clock;
  `alerts.json` single-model update + cross-model recompute (D-22 rule 1);
  shortlist migration from flat lists (D-15); `run_update` subprocess
  construction per named type (subprocess mocked).
- **Fixture**: recorded GitHub `releases/latest` payloads (current, newer,
  malformed, rate-limited 403); existing `docs/sample/` activity CSVs for
  `calibrate_token_weights` parity.
- **Mocked integration**: MCP tools invoked in-process (existing
  `tests/test_mcp.py` pattern) with `monkeypatch`/`tmp_path` for config and
  data dirs; `requests` patched — no live network; timeout and
  exception paths prove the tool call still succeeds.
- **Regression**: F-2 (manual add survives Hermes sync, D-2), F-3 (unknown
  model), F-10 (divergence parity), F-15/F-16 (fake-slug drop and prefix
  substitution), F-19 (no implicit default), registry-vs-docs drift test,
  CLI↔MCP parity test, annotation-presence test, zero-network test for
  local reads.
- **Live** (`@pytest.mark.live`, opt-in only): one real `releases/latest`
  contract test.
- **Manual evidence** (not CI): E-1/E-3 host behavior, captured as artifacts.
- **Manual release gates** (not CI, by design): MG-1 MCP Inspector ritual
  with its checklist, MG-3 `hermes mcp test anticharon`, and MG-2 PO release
  sign-off (§6); results are recorded in this ledger and excluded from
  `uv run pytest`.
- `uv run pytest` passes; suite stays < 30 s; lint gate per
  `.agents/skills/linting/SKILL.md`.

---

## 8. Non-Goals

- PyPI publishing (see candidate CAND-1).
- Filesystem watchers / hot reload (rejected in the self-update request).
- Any write to Hermes configuration (one-way invariant stays).
- Out-of-scope BACKLOG items listed in §1.
- Legacy lint debt remediation (Rule 13).
- Resolving or pricing alias proxy models (`~vendor/…-latest` with
  `alias_target`): their price does not reflect a stable model, which
  undermines price transparency, so this sprint does not handle them
  (PO, 2026-09-24). Exact match treats them like any other slug.

---

## 9. Candidate Additions (found during planning; not in scope unless the PO pulls them in)

Reactive to the two input documents only.

- **CAND-1 PyPI distribution** — listed as an alternative in the self-update
  request; would make installs resolve new releases via HTTP caching
  and simplify E-2's matrix. Separate packaging decision.
- ~~CAND-2 `anticharon version --check`~~ — superseded by SELFUP-1 CLI
  `anticharon check-updates`.
- ~~CAND-3 Rename `priceWarnings` → `price_warnings`~~ — pulled into scope as A2A-8 (D-1c).
- **CAND-4 Publish the missing `v0.5.4` GitHub Release** — gap found in E-4
  prep (F-12); release-housekeeping, PO action.
- **CAND-5 Shortlist-quality advisories on `add_model`** — from eval draft
  Stories 1–2: when an agent adds a slug, emit `A2A` messages for volatile
  aliases (`:latest`, `:free`) and cold-start models (< 15 days since
  catalog `created`). Pure rule checks on data `add_model` already fetches;
  no eval engine, no scoring. Ergonomic, but it borrows eval semantics —
  PO call.
- **CAND-6 Stale eval-draft references** — Story 3 cites the retired
  `tests/run_tests.py` and a non-existent `tests/sample/`; fix inside the
  draft when the eval initiative is picked up (the draft moves to `.local/`
  under DOC-6, so no public change needed now).
- **CAND-7 (`a5`) Vendor-neutral review host** — cross-vendor independent
  review needs the code on GitHub first (a cloud session's private disk is
  vendor-locked). Process/governance, not product scope.
- **CAND-8 (`a6`) "Review bundle branch" pattern** — merge the plan-doc
  branch into the code branch so an isolated reviewer syncs everything once;
  candidate for `AGENTS.md` Rule 4. Process/governance, not product scope.
- **CAND-9 Docs release gate** (D-8): agent-facing documentation now spans
  `llms.txt`, prompts, the agent skill, README and tool descriptions; a
  release-time consistency gate (beyond the registry-vs-docs test) may be
  needed as these grow.
- Prior-session `a4` is already in scope as DOC-2; the prior "item 9"
  (config path resolution) was withdrawn in that session as pre-existing
  backlog and is not carried here.

---

## Deferred / Still Open for a Future Planning Round

- **PARKED — Statistical update cadence for `effective_prices.json`
  (PO, 2026-09-24; out of scope, may be considered later):** hypothesis —
  just as moving averages summarize prices for the user, a moving variance
  per model could decide whether granular observations need a daily refresh
  or can be sampled every 3+ days (stable models refresh less often),
  reducing per-model network calls on `run`.
- **PARKED — Multi-config / nested sub-agent support (A-4, D-25):** per-call
  `config`/`data_dir` overrides on MCP tools for orchestrators running
  several sub-agents with separate shortlists (e.g. early OpenClaw
  adoption), and finer control over which default wins when Hermes and a
  manual default coexist. Revisit only with a real user scenario.
- **PARKED — `uvx` support (D-27):** ephemeral/cached execution via
  `uvx --from git+…`; unsupported and undocumented this sprint.
- **PARKED — Automatic update checks (D-9b):** background/cached version
  checks (24 h TTL, `~/.cache/anticharon/update_check.json`, opt-out env)
  and in-band `UPDATE_AVAILABLE` on every response, per the original
  self-update request — next planning round, after real-world testing of
  SELFUP-1/2.
- **TRACKED — Tool-annotation draft SEPs (ANN-5):** keep SEP #1913 (open
  draft), #1984, #1561, #1560, #1487 (closed as of 2026-09-24) on the radar;
  implement only if one enters the MCP spec or otherwise stabilizes.
- **PARKED — `canonical_slug` drift investigation (D-16):** confirm whether
  OpenRouter ever re-points a stable `id` to a new dated `canonical_slug`
  for non-alias models (monitor stored vs. live values once MCP-8 ships).
  If proven, apply the D-16 policy: key history by `canonical_slug`, refresh
  and backfill the new canonical as its own series, no warning, no mixed
  history. Moved to `docs/BACKLOG.md` at sprint close.
- **PARKED — W1 out-of-scope findings (implementation agent, 2026-09-25;
  not implemented, awaiting PO triage):** (1) `model discover` /
  `discover_models` return an empty list with `status: "success"` and no
  message when the catalog fetch fails (`fetch_catalog` returns `[]`);
  (2) `run`/`check` with OpenRouter unreachable **and** no `history.csv`
  return an empty `prices_shortlist` with no message (the fallback branch,
  and so `API_FALLBACK`, needs existing history) — relevant to MCP-6 (W2);
  (3) `calibrate` on a zero-token log silently keeps default weights —
  relevant to §3f (W4); (4) `anticharon test` reports an unreachable
  OpenRouter only as per-check data, with no message code.
- **DEFERRED — Legacy Ruff findings inventory (2026-09-25; linting policy):**
  `ruff check src tests --statistics` reports 39 findings: 21 BLE001, 8 B023,
  3 S110, 2 PLW1510, 2 RUF059, 1 SIM102, 1 S112, and 1 F841.
  Affected files (finding count → codes): `src/anticharon/analytics.py` (3 →
  RUF059×2, SIM102); `cli.py` (5 → BLE001×3, S110, S112); `config.py` (2 →
  BLE001, S110); `discovery.py` (9 → B023×8, BLE001); `hermes.py` (5 →
  BLE001×2, F841, PLW1510×2); `mcp.py` (2 → BLE001, S110);
  `storage.py` (2 → BLE001×2); `tester.py` (8 → BLE001×8);
  `tracker.py` (3 → BLE001×3). Existing findings remain deferred under
  `AGENTS.md` Rule 13; W2 adds no unresolved finding on its changed lines.
- Everything in §8 and the OUT rows of §1 remain in `docs/BACKLOG.md`,
  untouched by this sprint.


---

## 10. Wave Execution and Ledger Register

This sprint runs on the single branch `codex/mcp-ecosystem-ergonomics`. There
are no per-wave implementation branches, test branches, worktrees, or PRs.
Only one implementation wave and one implementation agent are active at a
time. From Wave 2 onward, independent review/audit or pre-test planning may
run in parallel, but those activities are read-only and cannot modify code,
tests, or the ledger. No deliberately failing tests are accepted.

### Issue registration gate — before Wave 1

All 12 GitHub issues represented by `ISSUES_DRAFT.md` were created before
Wave 1. Their actual numbers are recorded below and in the issue-draft
companion. The issue register is committed atomically before implementation.
The control plane uses only the actual numbers recorded here; draft map IDs
are not GitHub issue numbers. No wave starts while an in-scope issue is
unregistered.

| Draft ID | Issue title | GitHub issue | Registration status |
|---|---|---:|---|
| 1 | Unified agent message contract (`messages` + `isError`) | #12 | Registered |
| 2 | Separate `check` / `history` / `run` with persisted alerts | #13 | Registered |
| 3 | Source-tagged shortlist, Hermes order and explicit defaults | #14 | Registered |
| 4 | Exact-match slugs: no silent drops or substitutions | #15 | Registered |
| 5 | CLI/MCP parity tools: shortlist, calibration, self-test, conditional OpenClaw import | #16 | Registered |
| 6 | MCP tool annotations, server identity and descriptions | #17 | Registered |
| 7 | Prompt parity on the CLI and prompt hardening | #18 | Registered |
| 8 | Fallback-aware alerts and fallback-order display (spike first) | #19 | Registered |
| 9 | Experimental self-update: `check_updates` + `run_update` | #20 | Registered |
| 10 | Documentation truth pass: single `llms.txt`, install docs, Beta, agent skill | #21 | Registered |
| 11 | Governance: protocol-baseline rule, pre-work cleanup | #22 | Registered |
| 12 | Release v0.6.0 Beta: manual gates and sign-off | #23 | Registered |

Formal GitHub issue relationships mirror the dependency plan. `Blocked by` is
set on the downstream issue; the shared sprint branch is not individually
attached to each issue.

| GitHub issue | Blocked by |
|---:|---|
| #12 | — |
| #13 | #12 |
| #14 | #12 |
| #15 | #12 |
| #16 | #12, #14 |
| #17 | #13, #16 |
| #18 | #16 |
| #19 | #13, #14 |
| #20 | #12 |
| #21 | #12–#20 |
| #22 | — |
| #23 | #12–#22 |

### Wave order and traceability gates

Run waves serially in this order: W1 Foundation → W2 Model identity → W3
Command split → W4 Tool surface → W5 Host integrations → W6 Fallback alerts
→ W7 Docs & release. Each wave starts from the current integrated HEAD of
the sprint branch, not a pinned base SHA.

Before each wave starts, perform a brief ledger-to-wave traceability check:
confirm every issue number is registered, each listed issue maps to the
wave's ledger IDs, dependencies and OPEN decisions are understood, and scope
contains no additions not approved by the PO. Record the starting commit and
traceability result in that wave's closeout record below. Code agents may
suggest new scope in chat; unapproved suggestions go only in the parked
section and do not enter a wave.

Each wave follows design → implementation with tests → audit/review. Tests
are written and integrated on this same branch as part of the wave; the
verification gate must be green before any wave-close commit. If a gate fails,
fix it or stop the wave without marking it complete. A read-only audit may be
parallel from W2 onward; no parallel implementation or test-writing lane.

At wave end, transfer the complete sidecar state into this ledger before
closing the wave. This includes progress/gates, done IDs and evidence, open
questions and their status, out-of-scope findings, verification commands and
results, decisions/PO responses, and next-wave resume context. Identify the
atomic implementation and closeout commit SHAs and the actual GitHub issue
numbers. Sidecars are handoff aids; after closeout this ledger is the durable
record. Every change of scope or acceptance requires PO sign-off and a ledger
update before implementation proceeds.

### Wave closeout register

Fill one record at each wave close. Do not mark a wave complete until all
fields are transferred from its sidecar and the green verification result is
recorded.

| Wave | GitHub issues | Ledger IDs traced | Start commit | Atomic implementation commit(s) | Green verification (command/result) | Audit/review findings and disposition | Decisions / PO sign-off | Open questions / parked findings | Sidecar state transferred | Closeout commit | Next-wave handoff |
|---|---|---|---|---|---|---|---|---|---|---|---|
| W1 Foundation | #12, #22 | A2A-1…8, DOC-6, DOC-8 | `8fcbeeb` | `35d6398` | `uv run pytest` → 248 passed in 2.42s | 0 material violations | D-1e (PO, 2026-09-25) | 4 findings parked | YES | `35d6398` | W2 unblocked |
| W2 Model identity | #14, #15 | MCP-2/6/7/8, D-2/5/13/14/15/24/25 | `35d6398` | `053918a` | `uv run pytest` → 100% green | 0 material violations | D-13, D-18c (PO, 2026-09-25) | None | YES (bypassed sidecar) | `6123800` | W3 unblocked |
| W3 Command split | #13 | MCP-10/11, D-3/4/18/18b/18c/19/22/28 | `6123800` | `9fd6d41`, `9f088f0` | `uv run pytest` → 270 passed, 3 deselected in 1.15s | Gate R Conditional Pass (F-W3-1..4 resolved in `9f088f0`; F-W3-5 parked for W4). Incremental review PASS. | PO signed off on Gate R remediation and F-W3-5 parking | 3 findings parked: (1) discover_models no ZDR param; (2) parity test scope; (3) import_hermes_models default (F-W3-5 to W4) | YES | (Pending PO closeout) | W4 unblocked (depends on W2, W3 closed) |
| W4 Tool surface | #16, #17, #18 | MCP-1/3/4/5/9/12/13, §3f, §3b | `b58d4e2` | `05aaf32`, `a13bdcd` | `uv run pytest` → 287 passed, 3 deselected in 0.78s | Gate R Conditional Pass (Claude Code Sonnet 5: 3 findings resolved in `a13bdcd`). PASS. | §3f sum tolerance 0.000001 + normalization confirmed by PO; CLI prompt syntax approved | OpenClaw alpha importer deferred to W5; Ruff legacy findings (39) deferred | YES | `b4a52c3` | W5 unblocked (depends on W4 closed) |
| W5 Host integrations | #16, #20 | SELFUP-0…2, MCP-15, E-1…E-4 | `b4a52c3` | `bffd4f8`, `e315830` | `uv run pytest` → 294 passed, 3 deselected in 1.36s | Gate R Conditional Pass (Sonnet 5: 2 findings resolved in `e315830`). PASS. | PO approved named update types and parking OpenClaw; E-4 fixture recorded | OpenClaw alpha importer parked per PO decision; E-1..E-3 recorded | YES | (Pending PO closeout) | W6 unblocked (depends on W5 closed) |
| W6 Fallback alerts | #19 | MCP-14, E-5 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
| W7 Docs & release | #21, #23 | DOC-1/2/3/3a/5/7, MG-1/2/3 | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN | OPEN |
