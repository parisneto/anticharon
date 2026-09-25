# WAVE-2 Sidecar — Model identity

> Working handoff for W2. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #14 shortlist · #15 exact match
- **Ledger IDs:** MCP-2, MCP-6, MCP-7, MCP-8, D-2, D-5, D-13, D-14, D-15, D-24, D-25, F-2, F-3, F-10, F-15, F-16, F-19, DOC-4
- **Depends on:** W1
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
- [ ] Entries {model, source, order?}; flat lists migrate on next write
- [ ] Manual adds survive Hermes sync; Hermes-entry removal refused (SOURCE_MANAGED)
- [ ] No startswith fallback; no silent drops (per-model messages)
- [ ] `NOT_MONITORED` on local reads means only "not in shortlist" (no catalog query); `run --model` exact-filters shortlist and absent target → refused (`NOT_MONITORED`, no catalog or pricing request); `add_model` validates exact slug (`NO_EXACT_MATCH` if invalid)
- [ ] Default never inferred from position; NO_DEFAULT when absent; --default / default=true

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
- **Suggested implementation model:** Sonnet high
