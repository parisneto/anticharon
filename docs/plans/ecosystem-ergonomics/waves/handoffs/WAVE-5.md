# WAVE-5 Sidecar — Host integrations

> Working handoff for W5. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #20 self-update · #16 OpenClaw alpha importer (MCP-15, conditional)
- **Ledger IDs:** SELFUP-0, SELFUP-1, SELFUP-2, E-1, E-2, E-3, E-4, D-9, D-9b, D-26, D-27 · MCP-15 (see `docs/plans/ecosystem-ergonomics/openclaw_research.md`)
- **Depends on:** W4 closed (OpenClaw also requires W2 shortlist shape)
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** run_update final type set and mechanics (PO live tests); E-1…E-4 evidence; **OpenClaw: supported version, verified `models status --json` schema, selected-agent behavior, first acceptance fixture — or park**

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | Traceability confirmed at `b4a52c3`; #20 → SELFUP-0…2 and #16 → MCP-15. OpenClaw is parked because its PO-owned evidence remains OPEN. |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | Self-update implementation + deterministic tests complete; `uv run pytest` → 293 passed, 3 deselected in 1.33s. E-1…E-3 remain PO host/install evidence gates. |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [x] check_updates / check-updates: is_latest, ~2 s timeout, UPDATE_CHECK_FAILED + isError
- [x] run_update: EXPERIMENTAL always; named types; sys.executable -m pip fallback; subprocess mocked in tests
- [ ] E-1…E-4 results recorded in the ledger
- [x] OpenClaw alpha: Tier 1 `openclaw models status --json` (no `--probe`, no shell, 2 s timeout), Tier 2 fail-closed JSON5 scanner, never mutates OpenClaw config, never persists a partial shortlist, `import:openclaw` source tag — **or** recorded as parked in the ledger

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| 2026-09-26 | D / B | Codex | — | Implemented SELFUP-1/2 and recorded E-4/API evidence; E-1–E-3 await PO host/install-matrix verification; MCP-15 parked. |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| SELFUP-1 / D-26 | `test_check_updates_reports_is_latest_with_two_second_timeout` / `tests/test_updater.py:31`; `test_check_updates_failure_is_an_error_and_mcp_is_error` / `tests/test_updater.py:46` |
| SELFUP-2 / D-9 | `test_run_update_uses_running_interpreter_pip_fallback_and_experimental_warning` / `tests/test_updater.py:64`; `test_run_update_restart_host_runs_named_host_command` / `tests/test_updater.py:77`; `test_run_update_phoenix_sequences_are_mocked_and_named` / `tests/test_updater.py:92` |
| D-9b / D-27 | `test_cli_update_commands_preserve_envelope_parity` / `tests/test_updater.py:109`; implementation documents user-initiated-only behavior and excludes `uvx` |
| SELFUP-0 / E-4 | GitHub Releases API observation recorded in ledger §4; deterministic tests at `tests/test_updater.py:31-61` |
| E-1 / E-2 / E-3 | Recorded pending PO host/install-matrix evidence in ledger §4; not claimable from this workspace |
| MCP-15 | Parked in ledger §4: required OpenClaw version/schema/agent/fixture evidence remains OPEN |

## Open questions (blocking?)
- E-1, E-2, and E-3 need PO execution in Claude Desktop, Hermes, Cursor, and MCP Inspector / supported install modes before wave closeout.

## Findings outside scope
- _none_

## Verify
Run the required checks on the sprint branch. Do not close the wave unless all required gates pass.
```bash
uv run pytest
```

## Next
Before starting the next wave, transfer all fields above into the corresponding ledger §10 closeout row, including commit SHAs and actual GitHub issue numbers.
- **Suggested implementation model:** Codex high
