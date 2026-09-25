# WAVE-5 Sidecar — Host integrations (parallel)

> PRIVATE handoff for W5. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #9 self-update · #5 OpenClaw alpha importer (MCP-15, conditional)
- **Ledger IDs:** SELFUP-0, SELFUP-1, SELFUP-2, E-1, E-2, E-3, E-4, D-9, D-9b, D-26, D-27 · MCP-15 (see `docs/plans/ecosystem-ergonomics/openclaw_research.md`)
- **Depends on:** W1 (OpenClaw also needs W2 shortlist shape) — runs alongside W2–W4
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w5` · test lane: `codex/mcp-ecosystem-ergonomics-w5-tests`
- **PO-owned decisions inside this wave:** run_update final type set and mechanics (PO live tests); E-1…E-4 evidence; **OpenClaw: supported version, verified `models status --json` schema, selected-agent behavior, first acceptance fixture — or park**

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Codex high (isolated update.py) | ☐ |
| B Build | build | Codex high (isolated update.py) → PO live tests | ☐ |
| B Tests (parallel) | test | Gemini: E-4 release-payload fixtures (current, newer, malformed, 403); OpenClaw fixtures only from verified real output | ☐ |
| R Review | review | Claude /code-review high (other vendor than builder) | ☐ |

## Acceptance (from the ledger)
- [ ] check_updates / check-updates: is_latest, ~2 s timeout, UPDATE_CHECK_FAILED + isError
- [ ] run_update: EXPERIMENTAL always; named types; sys.executable -m pip fallback; subprocess mocked in tests
- [ ] E-1…E-4 results recorded in the ledger
- [ ] OpenClaw alpha: Tier 1 `openclaw models status --json` (no `--probe`, no shell, 2 s timeout), Tier 2 fail-closed JSON5 scanner, never mutates OpenClaw config, never persists a partial shortlist, `import:openclaw` source tag — **or** recorded as parked in the ledger

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
- **Recommended model:** Codex high (isolated update.py)
- **Continuation line:** "Read the WAVE-5 sidecar and the ledger IDs it cites. You are {model}/{effort} for W5 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
