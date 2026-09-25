# WAVE-4 Sidecar — Tool surface

> Working handoff for W4. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Draft issue IDs (not GitHub numbers):** #5 tools (OpenClaw part moved to W5) · #6 annotations · #7 prompts
- **Ledger IDs:** MCP-1, MCP-3, MCP-4, MCP-5, MCP-9, MCP-12, MCP-13, §3f, D-6, D-12, D-17, D-23, D-29, §3b
- **Depends on:** W2, W3
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** **§3f sum tolerance + normalize-within-tolerance — PO confirms before build**; CLI prompt syntax (record when built)

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☐ | |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☐ | |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [ ] add/remove/list_models, self_test; save by default
- [ ] `calibrate_token_weights` (server-local CSV path, A-1) and `calibrate_fast` (three weights, §3f validation), shared persistence, `.bak`
- [ ] Calibration-details MCP resource (components, sample log lines, derivation guidance, CLI fallback)
- [ ] All five ToolAnnotations on every tool; serverInfo.version; instructions
- [ ] Prompts single-sourced and exposed on CLI
- [ ] Parity test passes; only registered asymmetries A-1, A-3, A-4, A-5, A-8

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
- **Suggested implementation model:** Sonnet medium
