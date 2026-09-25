# Agent Playbook — Ecosystem Ergonomics (v0.6.0 Beta)

> The canonical [`EXECUTION_CONTRACT.md`](../EXECUTION_CONTRACT.md) is the
> authoritative ledger. This playbook routes one implementation agent through
> seven serial waves on the existing sprint branch
> `codex/mcp-ecosystem-ergonomics`. Wave handoffs are temporary working notes;
> all state must be transferred into the ledger before each wave closes.

## 1. Execution rules

- Use one branch: `codex/mcp-ecosystem-ergonomics`. Do not create per-wave or
  test branches, worktrees, or wave PRs. Commit verified atomic changes on the
  sprint branch.
- Work one wave and one implementation agent at a time. From W2 onward,
  read-only audits or pre-test reviews may run in parallel; they must not edit
  code, tests, or planning documents. There is no parallel test-writing lane.
- Issue registration is complete: the actual GitHub numbers are recorded in
  ledger §10 and the issue-register commit precedes Wave 1. Issue numbers in
  this wave map are the actual GitHub issue numbers.
- Before each wave, check issue-to-ledger-ID traceability, dependencies, OPEN
  decisions and scope against the ledger. Record the starting commit and the
  result in the ledger at closeout.
- Tests are developed/integrated as part of the wave on the same branch. The
  required test gate must be green before a wave is closed or a closeout commit
  is made. Never accept an intentionally failing test gate. Stop and fix a
  failure before proceeding.
- At wave end, transfer the full handoff state (progress, completed IDs and
  evidence, decisions, open questions, findings, verification, and next-wave
  context) into the ledger §10, identifying actual issue numbers and commit
  SHAs. Update the ledger before committing the closeout.
- Scope cannot be invented by an agent. Suggestions may be raised in chat and
  recorded only in the ledger's parked section until the PO approves and the
  ledger is updated.
- Keep spec, changelog, tests, and implementation synchronized per `AGENTS.md`.
  No push, tag, release, or merge to `main` without the required release gates
  and PO approval.

## 2. Seven-wave sequence

| Wave | GitHub issues (IDs registered in ledger §10) | Ledger scope | Dependencies / gate | Suggested build and audit routing |
|---|---|---|---|---|
| **W1 Foundation** | #12, #22 | A2A-1…8, D-1…D-1d, F-1/14/17/20, DOC-6/8 | Issue register complete | Opus high implementation; independent audit after reviewable state |
| **W2 Model identity** | #14, #15 | MCP-2/6/7/8, D-2/5/13/14/15/24/25, F-2/3/10/15/16/19, DOC-4 | W1 closed | Sonnet high implementation; parallel read-only audit allowed |
| **W3 Command split** | #13 | MCP-10/11, D-3/4/18/18b/18c/19/22/28 | W1, W2 closed | Opus high implementation; parallel read-only audit allowed |
| **W4 Tool surface** | #16 (excluding conditional OpenClaw), #17, #18 | MCP-1/3/4/5/9/12/13, §3f, D-6/12/17/23/29, §3b | W2, W3 closed; PO confirms §3f tolerance before build | Sonnet medium implementation; parallel read-only audit allowed |
| **W5 Host integrations** | #20; #16 OpenClaw alpha (conditional) | SELFUP-0…2, E-1…E-4, D-9/9b/26/27, MCP-15 | W4 closed. OpenClaw version/schema/agent/acceptance remain OPEN; park importer absent evidence and PO acceptance. | Codex high implementation; PO live tests and independent audit |
| **W6 Fallback alerts** | #19 | MCP-14, E-5, D-5 | W2, W3 closed; E-5 PO decision | Sonnet medium spike/implementation; parallel read-only audit allowed |
| **W7 Docs & release** | #21, #23 | DOC-1/2/3/3a/5/7, D-7/8/27, MG-1/2/3 | All prior waves closed | Gemini Pro high docs; independent full-branch audit |

The fixed order is W1 → W2 → W3 → W4 → W5 → W6 → W7. Dependencies are
rechecked in the pre-wave traceability gate. The two intentionally OPEN
decision groups remain: §3f calibration tolerance before W4 build, and MCP-15
OpenClaw evidence/PO acceptance during W5 (otherwise parked).

## 3. Wave gates

1. **Start / traceability:** Read the ledger and the wave handoff. Confirm all
   actual issue numbers are present in §10; map each issue to the listed ledger
   IDs; confirm dependencies and OPEN decisions; confirm no unapproved scope.
   Record start commit and check result in the ledger closeout row.
2. **Design:** Identify impacted spec sections, implementation areas, tests,
   and acceptance evidence. Resolve only decisions already assigned to this
   wave; escalate other decisions to the PO.
3. **Implementation and verification:** Implement only approved scope, update
   spec and changelog, add deterministic tests, then run required checks. Do
   not report wave completion unless `uv run pytest` and applicable required
   quality gates pass. The suite must never be intentionally left failing.
4. **Audit/review:** After a reviewable implementation exists, read-only audits
   may run in parallel from W2 onward. Record every finding and its disposition
   in the ledger. The implementation agent resolves approved in-scope findings.
5. **Closeout:** Copy all sidecar state into ledger §10, including evidence by
   ledger ID, verification command/result, audit outcomes, PO decisions, open
   items, commit SHAs, and next-wave context. Commit the atomic implementation
   unit(s) and ledger closeout; only then start the next wave.

## 4. Kickoff prompt

```text
ROLE: Anticharon implementation agent for Ecosystem Ergonomics v0.6.0 Beta.
WAVE: W{n} — {name}.
BRANCH: codex/mcp-ecosystem-ergonomics (single sprint branch).

READ FIRST:
1. AGENTS.md.
2. docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md — scope, decisions,
   §10 issue register and wave closeout.
3. docs/plans/ecosystem-ergonomics/ISSUES_DRAFT.md — planning map only.
4. docs/plans/ecosystem-ergonomics/waves/handoffs/WAVE-{n}.md.

BEFORE WORK: perform and record the ledger-to-wave traceability check. Confirm
actual GitHub issue numbers are registered, dependencies are closed, OPEN
decisions are understood, and scope is approved. If not, stop.

RULES: implement only the listed ledger IDs; no new scope. Update the spec
and [Unreleased] changelog with behavior changes. Add deterministic tests. Do
not create wave/test branches or worktrees. No intentional failing tests.
Run the required gate and get green before closeout. Parallel agents, if used,
are read-only auditors/pre-test reviewers only. Record suggestions outside
scope as parked in the ledger after PO awareness/approval.

AT WAVE END: transfer the complete handoff state into ledger §10, including
all evidence, questions, findings, decisions, test results, and commit SHAs.
Commit atomic verified changes and ledger closeout; do not start the next wave
until the ledger is current and the gate is green.
```

## 5. Handoff fields

Each `handoffs/WAVE-n.md` is a working checklist with: assigned issue IDs and
ledger IDs; dependencies; PO-owned decisions; phase progress; completed IDs
with evidence; open questions; findings; verification results; and next-wave
resume context. Update it while the wave runs. Before closing, transfer every
field and its final state into the matching row in ledger §10. The ledger, not
the handoff file, is the durable record.
