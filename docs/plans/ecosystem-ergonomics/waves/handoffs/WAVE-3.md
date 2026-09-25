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
| D Design | One implementation agent; ledger/spec traceability | ☐ | |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☐ | |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [ ] check/history make zero network calls
- [ ] run/run_prices write history.csv, effective_prices.json, alerts.json; --model/--dry-run/--force/--zdr
- [ ] ZDR never persisted; no --zdr on check
- [ ] Spec §5 three files, §7 commands updated

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
- **Suggested implementation model:** Opus high
