# WAVE-6 Sidecar — Fallback alerts

> Working handoff for W6. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #19
- **Ledger IDs:** MCP-14, E-5, D-5
- **Depends on:** W2, W3
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** E-5 display order and alert thresholds (PO)

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | #19 maps to MCP-14, E-5, D-5; E-5 observations recorded in ledger §4. |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | `uv run pytest` → 297 passed, 3 deselected in 2.43s. |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [ ] E-5 evidence + PO decision recorded in the ledger
- [ ] Next-fallback alert persisted in alerts.json; suppressed with no default
- [ ] Unpriceable fallbacks handled explicitly

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| | | | | |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| MCP-14 | `test_run_persists_next_hermes_fallback_cost_alert` / `tests/test_alerts_and_same_day.py:137`; `test_run_records_unpriceable_next_hermes_fallback_without_crashing` / `tests/test_alerts_and_same_day.py:156` |
| E-5 | Prototype observation / `docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md:581` |
| D-5 | Hermes-order assertion / `tests/test_alerts_and_same_day.py:137` |

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
- **Suggested implementation model:** Spike: Sonnet med prototype
