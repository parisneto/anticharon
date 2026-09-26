# WAVE-4 Sidecar — Tool surface

> Working handoff for W4. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues and ledger IDs:**
  - #16 tools (OpenClaw part moved to W5): MCP-1, MCP-5, MCP-13, §3f, D-6, D-12, D-17, D-29
  - #17 annotations, identity, descriptions: MCP-3, MCP-4, MCP-9, D-23, §3b
  - #18 prompts: MCP-12
- **Depends on:** W2, W3
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** §3f is resolved by the W4 task directive (`0.000001`, normalize within tolerance). CLI prompt syntax selected: `anticharon prompt <name> --arg KEY=VALUE`.

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | Baseline b58d4e2; scope checked against issues #16–#18; §3f tolerance/normalization implemented as directed in W4 task |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | See Done table; deterministic cases added |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [x] add/remove/list_models, self_test; save by default
- [x] `calibrate_token_weights` (server-local CSV path, A-1) and `calibrate_fast` (three weights, §3f validation), shared persistence, `.bak`
- [x] Calibration-details MCP resource (components, sample log lines, derivation guidance, CLI fallback)
- [x] All five ToolAnnotations on every tool; serverInfo.version; instructions
- [x] Prompts single-sourced and exposed on CLI
- [x] Parity test passes; only registered asymmetries A-1, A-3, A-4, A-5, A-8

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| | | | | |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| MCP-1 / D-12 / D-29 | `test_add_model_catalog_unavailable_does_not_persist`, `tests/test_mcp_w4.py:82` |
| MCP-3 / MCP-4 | `test_every_registered_tool_declares_all_five_annotations`, `tests/test_command_parity.py:98`; `test_server_identity_has_version_and_instructions`, `tests/test_command_parity.py:119` |
| MCP-5 / §3f / D-6 / D-17 | `test_calibrate_fast_normalizes_and_backs_up_config`, `tests/test_mcp_w4.py:15`; `test_calibrate_fast_rejects_out_of_tolerance_sum_without_mutation`, `tests/test_mcp_w4.py:31`; `test_calibrate_token_weights_uses_local_csv_and_backup`, `tests/test_mcp_w4.py:44` |
| MCP-9 / D-23 / §3b | `test_every_registered_tool_declares_all_five_annotations`, `tests/test_command_parity.py:98` |
| MCP-12 | `test_prompt_registry_covers_five_mcp_prompts`, `tests/test_command_parity.py:112`; `test_cli_prompt_registry_lists_and_renders`, `tests/test_mcp_w4.py:99` |
| MCP-13 | W4 tool parameter rows and registration assertion, `tests/test_command_parity.py:73`; `test_self_test_wraps_json_diagnostics_without_stdout`, `tests/test_mcp_w4.py:121` |
| Audit follow-up | `test_every_registered_tool_declares_all_five_annotations`, `tests/test_command_parity.py:98`; MCP-only registration and A-1 tie checked by `test_check_history_run_mcp_tools_are_registered`, `tests/test_command_parity.py:73`; `test_self_test_wraps_json_diagnostics_without_stdout`, `tests/test_mcp_w4.py:121` |
| D-29 | `test_import_hermes_tool_defaults_to_persist`, `tests/test_mcp_w4.py:68` |
| Calibration resource | `test_calibration_details_resource_is_registered_and_actionable`, `tests/test_mcp_w4.py:60` |

## Open questions (blocking?)
- _none_

## Findings outside scope
- **Deferred legacy lint debt (not introduced by W4):** `ruff check src tests --statistics` → 39 findings. Affected files: `src/anticharon/analytics.py` → 3 (`RUF059×2`, `SIM102`); `cli.py` → 5 (`BLE001×3`, `S110`, `S112`); `config.py` → 2 (`BLE001`, `S110`); `discovery.py` → 9 (`B023×8`, `BLE001`); `hermes.py` → 5 (`BLE001×2`, `F841`, `PLW1510×2`); `mcp.py` → 2 (`BLE001`, `S110`); `storage.py` → 2 (`BLE001×2`); `tester.py` → 8 (`BLE001×8`); `tracker.py` → 3 (`BLE001×3`). `scripts/lint_gate.py b58d4e2507de21acf0bd523becdc6ac94a2d21e8` passed with no new changed-line findings.

## Verify
Run the required checks on the sprint branch. Do not close the wave unless all required gates pass.
```bash
uv run pytest
```
Result: **287 passed, 3 live tests deselected, 0.78s**. Changed-line lint gate passed against the W4 baseline SHA.

## Next
Before starting the next wave, transfer all fields above into the corresponding ledger §10 closeout row, including commit SHAs and actual GitHub issue numbers.
- **Suggested implementation model:** Sonnet medium
