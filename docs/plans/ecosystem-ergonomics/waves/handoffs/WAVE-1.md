# WAVE-1 Sidecar — Foundation

> Working handoff for W1. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #12 message contract · #22 governance
- **Ledger IDs:** A2A-1…8, D-1, D-1b, D-1c, D-1d, F-1, F-14, F-17, F-20 · DOC-6, DOC-8
- **Depends on:** —
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
- [ ] Every CLI --json and MCP payload has status, messages (never empty), elapsed_ms
- [ ] status error/refused → isError: true / exit 1
- [ ] Legacy keys removed; price_warnings renamed; tests migrated to message codes (disclosed)
- [ ] AGENTS.md Rule 4 protocol-baseline rule; pre-work draft moved to .local/

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
