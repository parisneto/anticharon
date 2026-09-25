# WAVE-3 Sidecar — Command split

> PRIVATE handoff for W3. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #2 check/history/run + alerts.json
- **Ledger IDs:** MCP-10, MCP-11, D-3, D-4, D-18, D-18b, D-18c, D-19, D-22, D-28
- **Depends on:** W1, W2
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w3` · test lane: `codex/mcp-ecosystem-ergonomics-w3-tests`
- **PO-owned decisions inside this wave:** none

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Opus high | ☐ |
| B Build | build | Opus high | ☐ |
| B Tests (parallel) | test | Sonnet med: zero-network tests for check/history, alerts.json rule 1 (single-model update + cross-model recompute), parity-test skeleton | ☐ |
| R Review | review | /code-review high + Codex high | ☐ |

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
```bash
uv run pytest
```

## Next
- **Next phase / lane:** D Design (build)
- **Recommended model:** Opus high
- **Continuation line:** "Read the WAVE-3 sidecar and the ledger IDs it cites. You are {model}/{effort} for W3 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
