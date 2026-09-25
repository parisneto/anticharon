# WAVE-4 Sidecar — Tool surface

> PRIVATE handoff for W4. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides; this file
> only records progress. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **Issues:** #5 tools (OpenClaw part moved to W5) · #6 annotations · #7 prompts
- **Ledger IDs:** MCP-1, MCP-3, MCP-4, MCP-5, MCP-9, MCP-12, MCP-13, §3f, D-6, D-12, D-17, D-23, D-29, §3b
- **Depends on:** W2, W3
- **Base:** `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
- **Branch / worktree:** `codex/mcp-ecosystem-ergonomics-w4` · test lane: `codex/mcp-ecosystem-ergonomics-w4-tests`
- **PO-owned decisions inside this wave:** **§3f sum tolerance + normalize-within-tolerance — PO confirms before build**; CLI prompt syntax (record when built)

## Routing
| Phase | Lane | Model / effort | Status |
|---|---|---|---|
| D Design | build | Sonnet med (#5) | ☐ |
| B Build | build | Sonnet med (#5) · Sonnet low (#6, #7) | ☐ |
| B Tests (parallel) | test | Sonnet low: annotation-presence test, calibrate parity on docs/sample fixtures, parity-test completion (tools, params, prompts) | ☐ |
| R Review | review | /code-review med + Codex med | ☐ |

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
```bash
uv run pytest
```

## Next
- **Next phase / lane:** D Design (build)
- **Recommended model:** Sonnet med (#5)
- **Continuation line:** "Read the WAVE-4 sidecar and the ledger IDs it cites. You are {model}/{effort} for W4 {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate."
