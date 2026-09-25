# WAVE-3 Sidecar — Command split

> Working handoff for W3. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #13 check/history/run + alerts.json
- **Ledger IDs:** MCP-10, MCP-11, D-3, D-4, D-18, D-18b, D-18c, D-19, D-22, D-28
- **Depends on:** W1, W2
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** none

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | Read AGENTS.md, EXECUTION_CONTRACT.md (D-3/D-4/D-18/D-18b/D-18c/D-19/D-22/D-28, MCP-10/11), this sidecar, AGENT_PLAYBOOK.md before writing code |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | See Done table; `uv run pytest` green |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | Not run in this session; open for a follow-up audit pass |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☑ | This edit + ledger §10 row |

## Acceptance (from the ledger)
- [x] check/history make zero network calls
- [x] run/run_prices write history.csv, effective_prices.json, alerts.json; --model/--dry-run/--force/--zdr
- [x] ZDR never persisted; no --zdr on check
- [x] Spec §5 three files, §7 commands updated

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| 2026-09-25 | D→B→Closeout | Claude (Sonnet 5, this session) | n/a | Split `check`/`history` into local-only reads (`read_check_result`/`read_history_result` in `tracker.py`); `run`/`run_prices` remains the only fetch-and-persist path, gained `--force`/`force` and the same-day skip rule; added `alerts.json` (D-22) with the Rule 1 filtered-run merge; removed `force_refresh` (D-3) and `--zdr`/`zdr_only` from check (D-28); fixed a data-loss bug where a persisting `run --model X` silently discarded every other model's `history.csv` row; new MCP tool `run_prices`; spec §5/§7/§10.1a/§10.2 and `llms.txt` (both copies) synced; new tests + MCP-11 CLI↔MCP parity test |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| D-19 | `tests/test_alerts_and_same_day.py::test_check_and_history_make_zero_network_calls`; `read_check_result`/`read_history_result` in `src/anticharon/tracker.py` |
| MCP-10 / D-18 | `tests/test_alerts_and_same_day.py::test_same_day_rerun_skips_per_model_fetch_unless_forced` |
| D-18c | `tests/test_alerts_and_same_day.py::test_run_model_filter_never_drops_other_models_history`; `tests/test_model_identity.py::test_default_is_explicit_and_unmonitored_run_refuses_before_network` (pre-existing, still green) |
| D-22 | `tests/test_alerts_and_same_day.py::test_run_persists_alerts_json_and_check_reads_it_verbatim`, `::test_run_model_filter_replaces_only_target_alerts_and_recomputes_cross_model` |
| D-28 | `tests/test_mcp.py::test_run_prices_zdr_preserves_three_price_distinction_deterministic`, `::test_run_prices_zdr_unroutable_never_recommended_deterministic` (ZDR moved off `check_prices`); `src/anticharon/tracker.py::_persist_alerts` never writes `POLICY_*`/ZDR-ranked `BEST_OPTION_CHANGED` |
| D-3 | `check_prices` signature in `src/anticharon/mcp.py` (no `force_refresh`); CHANGELOG `[Unreleased]` Removed |
| D-4 | `read_check_result`/`read_history_result` never call `fetch_openrouter_models`/`fetch_endpoint_policy_pricing` |
| D-18b | `check` parser has no `--dry-run` in `src/anticharon/cli.py::build_parser`; `run`'s `dry_run` keeps "do the work, persist nothing" |
| MCP-11 | `tests/test_command_parity.py` (new); §3a implemented for `check`/`history`/`run` |

## Open questions (blocking?)
- _none_

## Findings outside scope
- `model discover --zdr` has no MCP `discover_models` parameter for it (pre-existing asymmetry, predates W3). Not touched here -- `discover_models` hardening is MCP-3/W4 territory; noted for the PO/W4 agent rather than fixed under W3's ledger IDs.
- `import_hermes_models`/`discover_models` are not yet covered by the new MCP-11 parity test (`tests/test_command_parity.py` is scoped to the W3 command-split pairs); a future wave touching those tools should extend `PARITY_ROWS`.

## Verify
Run the required checks on the sprint branch. Do not close the wave unless all required gates pass.
```bash
uv run pytest
```
Result: 270 passed, 3 deselected (`@pytest.mark.live`) in ~1-7s (well under the 30s gate). Deterministic lint gate (`ruff check` cross-referenced against this wave's changed lines) clean; `read_alerts`'s exception handling narrowed to `(OSError, ValueError)` to avoid a new BLE001 finding without needing a baseline exemption.

## Next
Before starting the next wave, transfer all fields above into the corresponding ledger §10 closeout row, including commit SHAs and actual GitHub issue numbers.
- **Suggested implementation model:** Opus high
