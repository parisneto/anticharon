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
| D Design | One implementation agent; ledger/spec traceability | ☐ | |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☐ | |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [ ] check_updates / check-updates: is_latest, ~2 s timeout, UPDATE_CHECK_FAILED + isError
- [ ] run_update: EXPERIMENTAL always; named types; sys.executable -m pip fallback; subprocess mocked in tests
- [ ] E-1…E-4 results recorded in the ledger
- [ ] OpenClaw alpha: Tier 1 `openclaw models status --json` (no `--probe`, no shell, 2 s timeout), Tier 2 fail-closed JSON5 scanner, never mutates OpenClaw config, never persists a partial shortlist, `import:openclaw` source tag — **or** recorded as parked in the ledger

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| | | | | |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| | |

## Open questions (blocking?)
- _none_

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
