# WAVE-7 Sidecar — Docs & release

> Working handoff for W7. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #21 docs · #23 release
- **Ledger IDs:** DOC-1, DOC-2, DOC-3, DOC-3a, DOC-5, DOC-7, D-7, D-8, D-27 · MG-1, MG-2, MG-3
- **Depends on:** all
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** MG-2 PO sign-off

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | W7 IDs map only to registered #21 and #23; all dependencies closed at `95528e0`. |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | `uv run pytest` → 302 passed, 3 deselected in 1.27s. |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☑ | Gate R found missing `UP_TO_DATE` coverage; remediation adds the code and AST-based conditional-code extraction. |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [x] Single root llms.txt in the wheel; spec §5/6/7/10, README, BACKLOG consistent
- [x] No uvx; ~/$HOME paths; Beta declared
- [ ] MG-1 Inspector ritual: ledger checklist (tools/resources/prompts, pass/fail + note, date, commit; no screenshots); MG-3 `hermes mcp test anticharon`; MG-2 PO sign-off

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| 2026-09-26 | D | Code Agent | - | Confirmed W7 traceability: DOC-1/2/3/3a/5/7, D-7/8/27 map to #21; MG-1/2/3 map to #23. |
| 2026-09-26 | B | Code Agent | - | Consolidated root llms.txt, installation/status docs, agent skill, prompt parity, and wheel packaging; 302 passed, 3 deselected. |
| 2026-09-26 | R | Independent audit / Code Agent | - | Resolved the confirmed `UP_TO_DATE` briefing omission and false-positive literal-only message-code test. |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| DOC-1 / D-7 | `test_root_llms_is_the_single_source_and_matches_the_mcp_resource` / `tests/test_docs_release.py:12`; `test_llms_lists_every_registered_mcp_surface_and_wheel_mapping` / `tests/test_docs_release.py:21`; `test_every_emitted_code_is_documented_in_llms_txt_and_spec` / `tests/test_agent_messages.py:497` |
| DOC-2 / DOC-5 | `test_prompts_use_mcp_actions_and_guard_remembered_defaults` / `tests/test_docs_release.py:52` |
| DOC-3 / DOC-3a / D-27 | `test_install_docs_are_beta_and_do_not_advertise_ephemeral_execution` / `tests/test_docs_release.py:37` |
| DOC-7 / D-8 | `test_install_docs_are_beta_and_do_not_advertise_ephemeral_execution` / `tests/test_docs_release.py:37`; `test_root_llms_is_the_single_source_and_matches_the_mcp_resource` / `tests/test_docs_release.py:12` |
| MG-1 | Inspector checklist recorded pending PO-host execution / `docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md:730` |
| MG-2 | PO sign-off pending manual gates / `docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md:771` |
| MG-3 | Hermes host test pending PO-host execution / `docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md:761` |

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
