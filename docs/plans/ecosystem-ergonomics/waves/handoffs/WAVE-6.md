# WAVE-6 Sidecar — Fallback alerts

> PRIVATE handoff for W6. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #8
- **Ledger IDs:** MCP-14, E-5, D-5
- **Depends on:** W2, W3
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w6` · test lane: `codex/mcp-ecosystem-ergonomics-w6-tests`
- **PO-owned decisions inside this wave:** E-5 display order and alert thresholds (PO)

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Spike: Sonnet med prototype | ☐ |
| B Build | build | Spike: Sonnet med prototype → PO decides → Sonnet med | ☐ |
| B Tests (parallel) | test | Gemini med: mixed-provider fallback-chain fixtures | ☐ |
| R Review | review | /code-review med + Codex med | ☐ |

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
- **Recommended model:** Spike: Sonnet med prototype
- **Continuation line:** "Read the WAVE-6 sidecar and the ledger IDs it cites. You are {model}/{effort} for W6 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
