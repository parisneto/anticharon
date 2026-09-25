# WAVE-1 Sidecar — Foundation

> Working handoff for W1. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #12 message contract · #22 governance
- **Ledger IDs:** A2A-1…8, D-1, D-1b, D-1c, D-1d, F-1, F-14, F-17, F-20 · DOC-6, DOC-8
- **Depends on:** —
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** none

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | Start commit `8fcbeeb3dd6f94b09477f6c46f446996e08fabbe` (PO-verified). Traceability: A2A-1…8 → #12, DOC-6/DOC-8 → #22 (ledger §10 register + this scope table); no W2+ IDs touched. Design gap (catalog missing codes) escalated and decided by the PO as D-1e (ledger §3d/§5) before implementation. |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | `uv run pytest`: 248 passed, 3 deselected (live), 2.42 s. Changed-line lint gate vs `8fcbeeb`: passed. |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [x] Every CLI --json and MCP payload has status, messages (never empty), elapsed_ms
- [x] status error/refused → isError: true / exit 1
- [x] Legacy keys removed; price_warnings renamed; tests migrated to message codes (disclosed)
- [x] AGENTS.md Rule 4 protocol-baseline rule; pre-work draft moved to .local/

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| 2026-09-25 | D | Claude Code implementation agent | n/a | Baseline SHA verified after PO push; traceability passed; PO decided D-1e (`HERMES_NOT_DETECTED`, `CALIBRATION_INPUT_INVALID`, `ZDR_LIVE_LIMITED`). |
| 2026-09-25 | B | Claude Code implementation agent | n/a | A2A-1…8, DOC-6, DOC-8 implemented with tests; spec §6.2/§7/§8/§10.1/§10.1a/§10.2, `llms.txt` (both copies), CHANGELOG `[Unreleased]` synced. |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| A2A-1 `AgentMessage` | `src/anticharon/models.py:14` · `tests/test_agent_messages.py::test_agent_message_to_dict_omits_unset_optionals` (`tests/test_agent_messages.py:95`) |
| A2A-2 envelope | `build_envelope` `src/anticharon/models.py:36` · `tests/test_agent_messages.py::test_build_envelope_orders_keys_and_appends_timed_completed` (:101), `::test_build_envelope_never_empty_and_error_completion_is_not_success` (:112), `::test_every_registered_mcp_tool_returns_the_envelope` (:165, registry-driven, also asserts no stdout in MCP mode), `::test_cli_json_outputs_carry_the_envelope_and_exit_zero` (:211, 9 CLI commands via real argparse), `::test_cli_test_json_carries_envelope` (:218) |
| A2A-3 `isError` / exit code | `ERROR_STATUSES` `src/anticharon/models.py:10`, `tool_result` `src/anticharon/mcp.py:34`, `_exit_code` `src/anticharon/cli.py:32` · `tests/test_agent_messages.py::test_tool_result_maps_error_statuses_to_is_error_with_same_body` (:133, real SDK call path), `::test_tool_result_passes_normal_statuses_through` (:127), `::test_cli_exit_code_follows_status` (:151), `::test_model_remove_absent_is_error_exit_one` (:245), `::test_self_test_failure_is_status_error_with_self_test_failed` (:232) |
| A2A-4 renderer | `render_messages` `src/anticharon/models.py:64`, used by `src/anticharon/cli.py`, `tester.py`, `discovery.py` · `tests/test_agent_messages.py::test_render_messages_prints_code_text_and_cli_action` (:411), `::test_check_human_output_says_detected_not_synced_and_renders_messages` (:386) |
| A2A-5 legacy keys removed | `src/anticharon/models.py` (`HermesIntegrationStatus`, `TrackerResult`), `manager.py`, `hermes.py:445` (`build_hermes_import_payload`, shared by CLI sync + MCP import) · `_assert_envelope` legacy-key check in every envelope test; `tests/test_agent_messages.py::test_cli_sync_and_mcp_import_return_the_same_payload` (:284), `::test_import_hermes_models_without_hermes_is_a_warning_not_an_error` (:187), `::test_cli_model_sync_without_hermes_is_warning_exit_zero` (:276) |
| A2A-6 divergence everywhere | `hermes_shortlist_divergent` / `hermes_detection_messages` `src/anticharon/hermes.py:399`/`:410`, used by `tracker.py:357` and `tester.py:109` · `tests/test_agent_messages.py::test_check_emits_order_sensitive_hermes_divergent` (:350), `::test_check_without_divergence_emits_no_hermes_warning` (:359), `::test_divergence_check_is_shared_with_self_test` (:365) |
| A2A-7 dry-run wording | `shortlist_write_message` `src/anticharon/hermes.py:432`, `PREVIEW_ONLY_RUN_MESSAGE` `src/anticharon/tracker.py:59`, `_print_hermes_line` `src/anticharon/cli.py:37` · `tests/test_agent_messages.py::test_run_persisting_hermes_sync_reports_shortlist_updated_then_unchanged` (:377), `::test_model_add_reports_persisted_vs_preview` (:258), `::test_check_human_output_says_detected_not_synced_and_renders_messages` (:386) |
| A2A-8 `price_warnings` | `src/anticharon/models.py:305` · `tests/test_agent_messages.py::test_check_prices_payload_uses_price_warnings_and_marks_preview` (:179); migrated `tests/test_cli.py:207`, `tests/test_mcp.py:187` |
| D-1e codes | `HERMES_NOT_DETECTED` `src/anticharon/hermes.py:410`; `CALIBRATION_INPUT_INVALID` `src/anticharon/cli.py:360`; `ZDR_LIVE_LIMITED` `src/anticharon/cli.py:487` · `tests/test_agent_messages.py::test_calibrate_invalid_input_returns_error_envelope_exit_one` (:298), `::test_calibrate_internal_failure_is_not_reported_as_invalid_input` (:319), `::test_discover_zdr_cap_is_a_zdr_live_limited_message` (:330), `tests/test_hermes.py::test_matrix_5_unavailable_cli_and_unavailable_file_is_standalone` (:493) |
| Other messages | `API_FALLBACK` `src/anticharon/tracker.py:65` · `tests/test_agent_messages.py::test_api_fallback_message_when_openrouter_unreachable` (:400); `NO_EXACT_MATCH` (transitional warning on `model add`) · `::test_model_add_unknown_slug_emits_no_exact_match` (:267); `calibrate --json` stdout regression · `::test_calibrate_json_is_pure_json_and_persists` (:308) |
| Docs sync (§6 WS-A2A) | spec §10.1a `docs/specs/spec_v1_anticharon.md:475`; `llms.txt` + `src/anticharon/llms.txt` (identical) · `tests/test_agent_messages.py::test_every_emitted_code_is_documented_in_llms_txt_and_spec` (:427) |
| DOC-6 pre-work cleanup | Draft copied to `.local/docs/specs/pre-work/draft_eval_harness.md` (byte-identical, `cmp` verified; git-ignored) then `git rm docs/specs/pre-work/draft_eval_harness.md`; `docs/BACKLOG.md:19` reworded without a private path; historical CHANGELOG mention untouched |
| DOC-8 protocol baseline | `AGENTS.md:37` (Rule 4 standing rule); spec §10.1 `docs/specs/spec_v1_anticharon.md:472` replaces the stale `mcp>=1.3.0 (FastMCP)` line (F-7) |

**Test changes disclosed (Rule 8):** assertions on removed keys migrated to message codes, never weakened: `tests/test_cli.py::test_discover_zdr_only_live_checks_models_matching_local_filters` (:87, also asserts only `COMPLETED`), `::test_discover_zdr_caps_live_checks_and_surfaces_warning` (:128, `zdr_warning` → `ZDR_LIVE_LIMITED`), `::test_cmd_run_json_output_preserves_three_price_distinction` (:207, `price_warnings`), `::test_cmd_model_sync_json_warns_and_preserves_shortlist_on_equal_length_incomplete` (:286, `warning` → `HERMES_INCOMPLETE` + `status: "warning"`), `::test_cmd_model_sync_human_warns_and_preserves_shortlist_on_equal_length_incomplete` (:313, warning now rendered on stdout via the shared renderer instead of stderr); `tests/test_mcp.py::test_import_hermes_models_warns_and_preserves_shortlist_on_equal_length_incomplete` (:111), `::test_check_prices_zdr_unroutable_never_recommended_deterministic` (:187), live-only `::test_mcp_server_suite` (`notice` → `PREVIEW_ONLY`; not run in the default gate); `tests/test_hermes.py` 10 tests (`hermes_integration.warning` → `HERMES_INCOMPLETE` / `HERMES_NOT_DETECTED` / `HERMES_DIVERGENT`, e.g. `::test_run_tracker_with_hermes_config_path` :159, `::test_matrix_4_incomplete_cli_and_unavailable_file_preserves_shortlist` :443, `::test_self_test_flags_hermes_shortlist_divergence` :646, `::test_self_test_reports_no_divergence_when_shortlist_matches` :675). No test skipped or removed.

## Open questions (blocking?)
- _none blocking._ Transitional (by design, for later waves): `model add` still adds a slug without an exact catalog match and flags it as `NO_EXACT_MATCH` at `warning` level (W4/D-14 makes it a refusal); `HERMES_DIVERGENT` compares the whole persisted shortlist until MCP-7 (W2) adds source tags.
- D-14/D-18c hard constraint: `run` has no `--model` option at this commit (added in W3 per D-18c), so no unmonitored-model live fetch path exists; W1 added none. The `refused` → `isError: true` / exit 1 mapping it needs is in place and tested.

## Findings outside scope
Recorded as PARKED in the ledger ("Deferred / Still Open"); not implemented:
- `model discover` / `discover_models` return an empty list with `status: "success"` when the catalog fetch fails (`fetch_catalog` returns `[]`); no message says so.
- `run`/`check` with OpenRouter unreachable **and** no `history.csv` return an empty `prices_shortlist` with no message (the fallback branch, and so `API_FALLBACK`, needs existing history). Relevant to MCP-6 (W2).
- `calibrate` on a log with zero tokens silently keeps default weights (relevant to §3f, W4).
- `anticharon test` reports an unreachable OpenRouter only as per-check data (`[WARN]`), with no message code.

## Verify
Run the required checks on the sprint branch. Do not close the wave unless all required gates pass.
```bash
uv run pytest
```
Result (2026-09-25, W1 implementation): `248 passed, 3 deselected in 2.42s`. Changed-line lint gate (`scripts/lint_gate.py` logic, base `8fcbeeb`): passed.

## Next
Before starting the next wave, transfer all fields above into the corresponding ledger §10 closeout row, including commit SHAs and actual GitHub issue numbers.
- **Suggested implementation model:** Opus high
