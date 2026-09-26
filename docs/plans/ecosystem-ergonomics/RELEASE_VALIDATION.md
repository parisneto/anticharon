# Ecosystem Ergonomics — Release Validation & MG-1 Inspector Report

## Validation Target

- **Initiative:** Ecosystem Ergonomics (`docs/plans/ecosystem-ergonomics/`)
- **Release Gate:** MG-1 (MCP Inspector Ritual)
- **Evaluator:** Product Owner (PO)
- **Target Version:** `v0.6.0-beta`
- **Gate Status:** **PASS** (remediated with in-flight fixes; follow-ups parked)

---

## 1. MG-1 MCP Inspector Ritual Matrix

The MCP Inspector ritual (`scripts/inspect_mcp.sh`) was executed against the release candidate. All active tools, resources, and prompt templates were inspected.

| Kind | Item | Result | Note |
|---|---|---|---|
| Tool | `check_prices` | **Pass** | Verified in Inspector. Clarification added to docstring noting local endpoint does not compute ZDR prices. |
| Tool | `run_prices` | **Pass** | Verified live fetch, alerts persistence, and ZDR evaluation (`zdr_only=true`). |
| Tool | `get_model_history` | **Pass** | Verified local 30-day analytics and format options (`json`, `csv`). |
| Tool | `discover_models` | **Pass** | Verified live OpenRouter catalog querying and filtering. |
| Tool | `add_model` | **Pass** | Verified shortlist insertion and catalog slug validation. |
| Tool | `remove_model` | **Pass** | Verified shortlist deletion and source-management guards. |
| Tool | `list_models` | **Pass** | Verified shortlist display (asymmetry with `action` key noted for future cleanup). |
| Tool | `import_hermes_models` | **Pass** | Verified one-way import safety and dry-run preview. |
| Tool | `import_openclaw_models` | **Not shipped** | Parked in W5 (2026-09-26). |
| Tool | `calibrate_token_weights` | **Pass** | Verified local CSV calculation (parked proposal to deprecate on MCP in favor of `calibrate_fast`). |
| Tool | `calibrate_fast` | **Pass** | Verified direct weight normalization and `.bak` configuration backup. |
| Tool | `self_test` | **Pass** | Verified diagnostic execution and structured JSON envelope. |
| Tool | `check_updates` | **Pass** | Remediated: SemVer tuple parsing resolves false downgrade notice when installed is ahead of latest release. |
| Tool | `run_update` | **Pass** | Remediated: added direct shell execution warning and documented all five `UpdateType` sequences inline. |
| Resource | `anticharon://llms.txt` | **Pass** | Verified content rendering and schema glossary. |
| Resource | `anticharon://history.csv` | **Pass** | Verified compact 30-day historical table read. |
| Resource | `anticharon://shortlist.json` | **Pass** | Verified configuration payload read. |
| Resource | `anticharon://calibration-details` | **Pass** | Verified derivation documentation and formulas. |
| Prompt | `cost_spike_triage` | **Pass** | Verified prompt template rendering with arguments. |
| Prompt | `model_migration_advisor` | **Pass** | Verified migration advisor arguments and output. |
| Prompt | `family_upgrade_discover` | **Pass** | Verified provider family discovery prompt. |
| Prompt | `daily_cost_briefing` | **Pass** | Verified executive cost briefing rendering. |
| Prompt | `budget_optimization_audit` | **Pass** | Verified budget audit prompt rendering. |

---

## 2. In-Flight Remediation (MG-1 Fixes)

During the MG-1 Inspector walkthrough, three ergonomic improvements were identified and resolved prior to commit:

1. **SemVer Comparison in `check_updates` (`src/anticharon/updater.py`):**
   - Replaced naive string equality (`installed_version == latest_version`) with numeric tuple parsing `_parse_version()`.
   - Condition `is_latest = installed_parsed >= latest_parsed` ensures that development or pre-release builds ahead of GitHub Releases evaluate to `is_latest: True`.
   - Contextual message emitted when ahead (`"Anticharon {installed_version} is ahead of the latest GitHub release ({latest_version})."`) without false downgrade actions.
2. **Regression Test Coverage (`tests/test_updater.py`):**
   - Added `test_check_updates_ahead_of_latest_reports_is_latest_true` (ahead version evaluation).
   - Added `test_check_updates_behind_latest_reports_update_available` (behind version evaluation).
3. **Tool Description Hardening & Clarification (`src/anticharon/mcp.py` & `llms.txt`):**
   - `check_prices`: Added explicit operational notice that Zero Data Retention (ZDR) is unsupported on the local cache-only endpoint, directing callers needing live ZDR data to `run_prices(zdr_only=true)`.
   - `run_update`: Removed inaccurate "only tool that executes commands" phrase; added explicit host shell execution warning; documented all 5 `UpdateType` sequences (`install_only`, `restart_host`, `phoenix`, `phoenix_inverted`, `reload_request`) inline.
   - Synchronized tool definitions in `llms.txt`.

### Test & Diagnostic Gate
- **pytest:** `uv run pytest` → 304 passed, 3 deselected in 1.34s.
- **ruff:** `uv run ruff check` → clean on all modified files.
- **self-test:** `uv run anticharon test` → all core diagnostics passed.

---

## 3. Parked Findings for Subsequent Sprint

The following cosmetic and architectural items were observed during the inspection and are intentionally parked:

1. **Root vs. Nested `action` Field Asymmetry:**
   - In `check_prices()`, corrective commands are nested inside message objects (`.messages[*].action` as a dictionary with `mcp` and `cli` keys).
   - In `list_models()`, `.action` is a root-level primitive string (`"list"`).
   - *Disposition:* Parked for schema normalization in v0.6.1+.
2. **`calibrate_token_weights` vs. `calibrate_fast` on MCP:**
   - `calibrate_fast` was added as the preferred MCP tool (avoiding server-local filesystem path requirements). Retaining `calibrate_token_weights` on MCP could cause confusion.
   - *Disposition:* Evaluate deprecating/hiding `calibrate_token_weights` from the MCP surface in favor of `calibrate_fast` in a future wave.
3. **ZDR Persistence in Stored History:**
   - `check_prices` reads purely local history and alerts, which do not currently preserve ephemeral provider-level ZDR routing availability.
   - *Disposition:* Requires an architectural evaluation on whether ZDR flags should be stored in `history.csv` / `effective_prices.json` or remain strictly live queries.

---

## 4. Proposed Commit Message

```git
fix(updater): use semver comparison in check_updates and clarify mcp tool contracts (MG-1)

- MG-1: resolve MCP Inspector findings during v0.6.0 release candidate ritual
- parse numeric semver tuples in check_updates to prevent false downgrade
  warnings when installed version is ahead of latest github release tag
- add regression tests for ahead and behind version checks in test_updater.py
- clarify run_update mcp description to warn of direct shell command execution
  and document the five UpdateType sequences inline
- sync run_update tool description in llms.txt
- add note to check_prices mcp tool clarifying lack of local ZDR support and
  directing callers to run_prices(zdr_only=true)
- record MG-1 walkthrough findings and parked items in RELEASE_VALIDATION.md
```
