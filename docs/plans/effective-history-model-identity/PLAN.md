# Implementation Plan

The [execution contract](EXECUTION_CONTRACT.md) owns acceptance, current
gate results, decision resolutions, and execution state. This plan owns
priority, sequencing, verification methods, rationale, and source references.

## Priority and recommended sequence

Preserve the proposed priority order: EH-1 and EH-2 are P0; EH-3…EH-6 are P1;
EH-7 is P2. Acceptance groups retain the exact EH-n/issue associations.

### Wave 1 — Correct the data contract

1. Reconcile the active specification's analytics section with shipped
   `effective_prices.json` backfill behavior.
2. D-1/D-2 (resolved, see contract): analytics read only dated
   `effective_prices.json` observations; maturity is the distinct observed-day
   count against `min_tracking_days_for_profile`, with no `first_seen` role.
3. Implement EH-1 with fixture-driven regression tests; prove E-2 using
   mature day-0, insufficient, and gapped real-history cases.
4. D-3 (resolved, see contract): Hermes owns the effective default while a
   manual preference is preserved. Implement EH-2 through the existing ownership model; prove E-3 by comparing
   persisted shortlist metadata with `model list --json`, including unchanged
   sequences, repeated syncs, and manual retention/default precedence.

### Wave 2 — Propagate trustworthy analytics

1. Evidence fields already exist on the analytics result (Wave 1); propagate them.
2. Make `run`, `history`, MCP, and agent prompts consume the same result (AC-3).
3. Prove E-4 with CLI/MCP analytics parity tests; update the active spec.

### Wave 3 — Model identity and catalog boundaries

1. Resolve D-4/D-5/D-6 for AC-4: persisted redirect schema, stable output/message
   contract, and deterministic retry/invalidation semantics.
2. Implement redirect persistence and `NOT_TRACKED`; prove E-5.
3. Add the local MCP resource (AC-5); prove E-6 for present/missing storage,
   read-only behavior, and no network.
4. Filter `:batch` only in normal discovery (AC-6); prove E-7 with exclusion
   and unchanged exact add/Hermes import cases.

### Wave 4 — CLI ergonomics and release readiness

1. Resolve D-7; implement the native help contract (AC-7).
2. Review top-level versus command-specific options; prove E-8 for primary
   and nested command forms, output, and exit codes.
3. Update examples, changelog, agent briefing, and tests.
4. Run E-9: full deterministic suite, applicable quality checks, and independent
   review against all AC-n groups and linked issues. CI currently runs pytest
   and the CLI diagnostic self-test; save evidence separately for checks CI
   does not run. Live tests remain opt-in.
5. Resolve D-8 before completion; perform preserved-backup VM verification
   (E-10) according to its approved mandatory/advisory role. Never replace user data.

## Document and closeout rule

Preserve only current truth; reference everything else. Update the contract's
current E-n results, D-n resolutions, execution row, and unresolved deferred
items at wave end. Reference durable evidence for the evaluated revision and
scope; do not transfer full handoff state or copy execution history.

Do not merge private investigation files into this public plan. Update the
active spec with implementation. Keep rationale here and current resolutions
in the contract; OPEN decisions block only their dependent work. Scope or
acceptance changes still require PO approval before implementation.

## Protocol baseline check

Finding (2026-10-02): the official [MCP versioning page](https://modelcontextprotocol.io/specification/versioning)
lists `2026-07-28` as the current revision; the pinned baseline is unchanged.
No newer revision is marked current. The baseline URL remains in the contract
under AGENTS.md Rule 4.

## Evidence and verification inputs

- VM reproduction and expected outcomes: GitHub [#25](https://github.com/parisneto/anticharon/issues/25)
  and [#26](https://github.com/parisneto/anticharon/issues/26).
- Analytics expectations: [#27](https://github.com/parisneto/anticharon/issues/27).
- Local MCP resource: [#28](https://github.com/parisneto/anticharon/issues/28).
- Redirect behavior: [#29](https://github.com/parisneto/anticharon/issues/29).
- Batch discovery: [#30](https://github.com/parisneto/anticharon/issues/30).
- CLI help reproduction: [#31](https://github.com/parisneto/anticharon/issues/31).
- Storage/analytics design: [active spec](../../specs/spec_v1_anticharon.md)
  and [pricing-engine-v2 contract](../pricing-engine-v2/EXECUTION_CONTRACT.md).

Detailed observations/results stay with their existing issue, review, CI run,
or durable verification artifact. Promote only necessary sanitized evidence
when no public owner exists. No new sidecar framework is needed.
