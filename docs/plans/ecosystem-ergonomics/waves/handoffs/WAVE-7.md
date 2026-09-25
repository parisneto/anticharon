# WAVE-7 Sidecar — Docs & release

> Working handoff for W7. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Draft issue IDs (not GitHub numbers):** #10 docs · #12 release
- **Ledger IDs:** DOC-1, DOC-2, DOC-3, DOC-3a, DOC-5, DOC-7, D-7, D-8, D-27 · MG-1, MG-2, MG-3
- **Depends on:** all
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** MG-2 PO sign-off

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☐ | |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☐ | |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [ ] Single root llms.txt in the wheel; spec §5/6/7/10, README, BACKLOG consistent
- [ ] No uvx; ~/$HOME paths; Beta declared
- [ ] MG-1 Inspector ritual: ledger checklist (tools/resources/prompts, pass/fail + note, date, commit; no screenshots); MG-3 `hermes mcp test anticharon`; MG-2 PO sign-off

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
- **Suggested implementation model:** Gemini Pro high (full-context drift audit + docs)
