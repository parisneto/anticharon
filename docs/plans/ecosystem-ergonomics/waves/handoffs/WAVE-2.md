# WAVE-2 Sidecar — Model identity

> Working handoff for W2. Updated by every agent at gates D, B, R. The ledger
> (`docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`) decides. This file
> is a temporary working note. Transfer its complete state to ledger §10 before
> wave close. Playbook: `../AGENT_PLAYBOOK.md`.

## Scope
- **GitHub issues:** #14 shortlist · #15 exact match
- **Ledger IDs:** MCP-2, MCP-6, MCP-7, MCP-8, D-2, D-5, D-13, D-14, D-15, D-24, D-25, F-2, F-3, F-10, F-15, F-16, F-19 fix, DOC-4
- **Depends on:** W1
- **Branch:** `codex/mcp-ecosystem-ergonomics` (continue from the current integrated HEAD)
- **PO-owned decisions inside this wave:** none

## Routing

One implementation agent works this wave. There is no parallel test-writing lane. From Wave 2 onward, parallel work is limited to read-only audit/pre-test review. The test gate must be green before wave close.
| Phase | Owner / activity | Status | Evidence / note |
|---|---|---|---|
| D Design | One implementation agent; ledger/spec traceability | ☑ | Traceability passed against baseline `35d6398c85df5fb08c9e971933e4f1c4de344832`; all requested IDs map to W2/#14/#15. Decisions D-2, D-5, D-13, D-14, D-15, D-18c, D-24, D-25, D-29 and F-19 fix reviewed. |
| B Build + tests | Same agent and sprint branch; no intentional failing gate | ☑ | 259 passed, 3 deselected; `uv run pytest`, 0.86s. |
| R Read-only audit/review | Independent audit after reviewable state; W2 onward may run audits in parallel | ☐ | |
| Closeout | Transfer all handoff fields to ledger §10; record commit SHAs and results | ☐ | |

## Acceptance (from the ledger)
- [x] Entries {model, source, order?}; flat lists migrate on next write
- [x] Manual adds survive Hermes sync; Hermes-entry removal refused (SOURCE_MANAGED)
- [x] No startswith fallback; no silent drops (per-model messages)
- [x] `NOT_MONITORED` on local reads means only "not in shortlist" (no catalog query); `run --model` exact-filters shortlist and absent target → refused (`NOT_MONITORED`, no catalog or pricing request); `add_model` validates exact slug (`NO_EXACT_MATCH` if invalid)
- [x] Default never inferred from position; NO_DEFAULT when absent; --default / default=true

## Progress log
| Date | Gate | Agent / model | Usage % before → after | Summary |
|---|---|---|---|---|
| 2026-09-25 | D/B | Codex implementation agent | — | Added source-tagged shortlist persistence, exact slug behavior, explicit defaults, local exact history reads, and deterministic W2 regressions. |

## Done (ledger ID → evidence)
| ID | Evidence (test name / file:line) |
|---|---|
| MCP-2 | `test_monitored_history_reads_local_storage_without_tracker_or_catalog`, `test_not_monitored_history_is_refused_without_catalog_or_price_fetch` — `tests/test_model_identity.py:127`, `:141` |
| MCP-6 | `test_tracker_reports_price_skip_reasons_per_model` — `tests/test_model_identity.py:99`; prefix regression `:86` |
| MCP-7 | `test_hermes_sync_preserves_manual_entries_and_order_and_rejects_manual_removal` — `tests/test_model_identity.py:26`; explicit source/default JSON `:159` |
| MCP-8 | `test_json_price_preserves_stored_identity_fields` — `tests/test_model_identity.py:159`; JSON serialization — `src/anticharon/models.py:222`, local history — `src/anticharon/mcp.py:147` |
| D-2 | `test_hermes_sync_preserves_manual_entries_and_order_and_rejects_manual_removal` — `tests/test_model_identity.py:26` |
| F-2 | Actual `add_model` followed by Hermes sync preserves the manual entry — `tests/test_model_identity.py:26` |
| D-5 | `test_divergence_compares_only_ordered_hermes_entries` — `tests/test_model_identity.py:45` |
| F-10 | CLI shared divergence regression — `tests/test_agent_messages.py:350`; manual exclusion/order case — `tests/test_model_identity.py:45` |
| D-13 | Hermes removal refusal — `tests/test_model_identity.py:26` |
| D-14 | Exact catalog and run filter behavior — `tests/test_model_identity.py:57`, `:72`, `:86` |
| F-3 | Exact local history reads and refusal — `tests/test_model_identity.py:127`, `:141` |
| D-15 | Flat-list migration on write — `tests/test_model_identity.py:12` |
| D-24 | No implicit default and `NO_DEFAULT` — `tests/test_model_identity.py:57` |
| D-25 | `test_manual_default_is_explicit_and_replacing_it_clears_old_default` — `tests/test_model_identity.py:112` |
| F-19 fix | `NO_DEFAULT` with no implied first-entry default — `tests/test_model_identity.py:57`; explicit manual default — `:112` |
| F-15 | Per-model price skip messages — `tests/test_model_identity.py:99` |
| F-16 | No prefix substitution — `tests/test_model_identity.py:86` |
| DOC-4 | Updated divergence behavior in `docs/specs/spec_v1_anticharon.md:323` |

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
- **Suggested implementation model:** Sonnet high
