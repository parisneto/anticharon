# WAVE-1 Sidecar — Foundation

> PRIVATE handoff for W1. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #1 message contract · #11 governance
- **Ledger IDs:** A2A-1…8, D-1, D-1b, D-1c, D-1d, F-1, F-14, F-17, F-20 · DOC-6, DOC-8
- **Depends on:** —
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w1` · test lane: `codex/mcp-ecosystem-ergonomics-w1-tests`
- **PO-owned decisions inside this wave:** none

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Opus high (#1) | ☐ |
| B Build | build | Opus high (#1) · Sonnet low (#11, separate branch) | ☐ |
| B Tests (parallel) | test | Sonnet med: §3d contract tests (serialization, status→isError, COMPLETED always present) · Gemini: fixtures for W2 (flat-list shortlists, fake slug) and W5 (release payloads) | ☐ |
| R Review | review | /code-review high + Codex high | ☐ |

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
```bash
uv run pytest
```

## Next
- **Next phase / lane:** D Design (build)
- **Recommended model:** Opus high (#1)
- **Continuation line:** "Read the WAVE-1 sidecar and the ledger IDs it cites. You are {model}/{effort} for W1 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
