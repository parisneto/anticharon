# WAVE-7 Sidecar — Docs & release

> PRIVATE handoff for W7. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #10 docs · #12 release
- **Ledger IDs:** DOC-1, DOC-2, DOC-3, DOC-3a, DOC-5, DOC-7, D-7, D-8, D-27 · MG-1, MG-2, MG-3
- **Depends on:** all
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w7` · test lane: `codex/mcp-ecosystem-ergonomics-w7-tests`
- **PO-owned decisions inside this wave:** MG-2 PO sign-off

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Gemini Pro high (full-context drift audit + docs) | ☐ |
| B Build | build | Gemini Pro high (full-context drift audit + docs) | ☐ |
| B Tests (parallel) | test | Sonnet low: registry-vs-docs drift test, llms.txt version test, CI wheel check | ☐ |
| R Review | review | Sonnet med (Rule 5/12 scan) + Codex high full-branch → MG-1, MG-3, MG-2 | ☐ |

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
```bash
uv run pytest
```

## Next
- **Next phase / lane:** D Design (build)
- **Recommended model:** Gemini Pro high (full-context drift audit + docs)
- **Continuation line:** "Read the WAVE-7 sidecar and the ledger IDs it cites. You are {model}/{effort} for W7 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
