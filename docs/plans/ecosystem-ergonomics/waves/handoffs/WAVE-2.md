# WAVE-2 Sidecar — Model identity

> PRIVATE handoff for W2. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #3 shortlist · #4 exact match
- **Ledger IDs:** MCP-2, MCP-6, MCP-7, MCP-8, D-2, D-5, D-13, D-14, D-15, D-24, D-25, F-2, F-3, F-10, F-15, F-16, F-19, DOC-4
- **Depends on:** W1
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w2` · test lane: `codex/mcp-ecosystem-ergonomics-w2-tests`
- **PO-owned decisions inside this wave:** none

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Sonnet high | ☐ |
| B Build | build | Sonnet high | ☐ |
| B Tests (parallel) | test | Sonnet med: regressions F-2, F-10, F-15, F-16, F-19 · Gemini: migration + fake-slug fixtures | ☐ |
| R Review | review | /code-review high + Codex high | ☐ |

## Acceptance (from the ledger)
- [ ] Entries {model, source, order?}; flat lists migrate on next write
- [ ] Manual adds survive Hermes sync; Hermes-entry removal refused (SOURCE_MANAGED)
- [ ] No startswith fallback; no silent drops (per-model messages)
- [ ] `NOT_MONITORED` on local reads means only "not in shortlist" (no catalog query); `run --model` absent target → refused + `isError` (`NOT_MONITORED` valid / `NO_EXACT_MATCH` unknown)
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
```bash
uv run pytest
```

## Next
- **Next phase / lane:** D Design (build)
- **Recommended model:** Sonnet high
- **Continuation line:** "Read the WAVE-2 sidecar and the ledger IDs it cites. You are {model}/{effort} for W2 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
