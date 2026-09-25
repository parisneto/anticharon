# Agent Playbook — Ecosystem Ergonomics (v0.6.0 Beta)

> PRIVATE (`.local/`, git-ignored). Operating manual for running the sprint
> with several agents/models, **one at a time**, in **7 waves**. The public
> source of truth stays `docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md`
> (the ledger) and `ISSUES_DRAFT.md`; this playbook only routes the work.
> Each wave has a sidecar handoff in `handoffs/WAVE-n.md`.
>
> **Base:** branch `codex/mcp-ecosystem-ergonomics` @ `ab41f72`
> ("docs: finalize ecosystem ergonomics sprint plan") — the canonical ledger.
> The earlier `claude/sprint-planning-ledger-b9e1af` draft is superseded.

## 1. The 7 waves

| Wave | Issues (draft #) | Ledger IDs | Depends on | Build lane | Test lane (parallel) | Review gate |
|---|---|---|---|---|---|---|
| **W1 Foundation** | #1 message contract · #11 governance | A2A-1…8, D-1…D-1d, F-1/14/17/20 · DOC-6, DOC-8 | — | Claude **Opus high** (#1) · Sonnet low (#11, own branch) | Sonnet med: §3d contract tests · **Gemini**: fixtures for W2/W5 | `/code-review` high + **Codex high** |
| **W2 Model identity** | #3 shortlist · #4 exact match | MCP-2/6/7/8, D-2/5/13/14/15/24/25, F-2/3/10/15/16/19, DOC-4 | W1 | Claude **Sonnet high** | Sonnet med: F-2/F-10/F-15/F-16/F-19 regressions; `NOT_MONITORED` local-only vs refused `run --model` (§3d) · Gemini: migration + fake-slug fixtures | `/code-review` high + **Codex high** |
| **W3 Command split** | #2 check/history/run + `alerts.json` | MCP-10/11, D-3/4/18/18b/18c/19/22/28 | W1, W2 | Claude **Opus high** | Sonnet med: zero-network, `alerts.json` rule 1, parity-test skeleton | `/code-review` high + **Codex high** |
| **W4 Tool surface** | #5 tools (minus OpenClaw) · #6 annotations · #7 prompts | MCP-1/3/4/5/9/12/13, §3f, D-6/12/17/23/29, §3b | W2, W3 · **§3f tolerance confirmed by PO before build** | Claude **Sonnet med** (#5: shortlist tools, `calibrate_token_weights`, `calibrate_fast`, calibration resource, `self_test`) · Sonnet low (#6, #7) | Sonnet low: annotation presence, §3f validation matrix, calibration parity on `docs/sample/`, parity-test completion | `/code-review` med + **Codex med** |
| **W5 Host integrations** ∥ | #9 self-update · #5 OpenClaw alpha (MCP-15, conditional) | SELFUP-0…2, E-1…E-4, D-9/9b/26/27 · MCP-15 | W1 only (OpenClaw also W2 shortlist shape) — **runs in parallel with W2–W4** | **Codex high** (`update.py`; OpenClaw Tier 1/Tier 2 adapter) → **PO live tests** on real Hermes/OpenClaw hosts | Gemini: E-4 release payloads; JSON5 / `models status --json` fixtures from **verified** output only | Claude `/code-review` high (other vendor). OpenClaw ships as alpha only with verified version/schema + PO acceptance case, else **parked** |
| **W6 Fallback alerts** | #8 | MCP-14, E-5, D-5 | W2, W3 | Spike: Sonnet med prototype → **PO decides** → Sonnet med | Gemini med: mixed-provider chain fixtures | `/code-review` med + Codex med |
| **W7 Docs & release** | #10 docs · #12 release | DOC-1/2/3/3a/5/7, D-7/8/27 · MG-1/2/3 | all | **Gemini Pro high** (full-context drift audit + docs) | Sonnet low: drift tests, `llms.txt` version test, wheel check | Sonnet med (Rule 5/12 scan) + **Codex high full-branch** → MG-1 Inspector checklist (no screenshots), MG-3, MG-2 |

Critical path: **W1 → W2 → W3 → W4 → W6 → W7**. W5 and every wave's test lane
run alongside. Opus is used only in W1 and W3.

**Ledger items still OPEN (resolve at the wave that needs them):**
- §3f calibration sum tolerance + normalize-within-tolerance → PO confirms
  **before W4 build**.
- MCP-15 OpenClaw supported version, output schema, selected-agent behavior,
  first acceptance fixture → evidence + PO acceptance **inside W5**, or park.

**Branching:** each wave branches from `codex/mcp-ecosystem-ergonomics`
(e.g. `codex/mcp-ecosystem-ergonomics-w1`, test lane `…-w1-tests`) and
returns to it through a PR after gate R; the base branch goes to `main` only
after W7 / MG-2 (Rule 11).

## 2. Inside every wave — 3 phases, 1 sidecar

```text
DESIGN  (design model)   plan + spec update                 → gate D  (sidecar)
BUILD ∥ TEST             build lane implements;             → gate B  (sidecar)
                         test lane writes tests in parallel
REVIEW  (other vendor)   self-review + /code-review + Codex → gate R  (sidecar) → PR
```

- **Model switches only at gates D, B, R** (max 3 per wave). Small waves may
  merge Design+Build on one model.
- **Never switch mid-phase.** At each gate, tests are either green or failing on
  purpose (test lane ahead of build), and the sidecar is updated.

### Parallel test lane rules (Rule 8 benefit: tests that don't mirror the code)
- Writes tests **only from** the ledger acceptance criteria, the §3d catalog and
  the wave's IDs — **must not read the build lane's implementation**.
- Own worktree/branch `<wave-branch>-tests`; touches **only** `tests/` and
  `tests/fixtures/`. Deterministic, no network.
- Tests failing before the build lands are expected. At gate B the test branch
  is merged into the build branch; any disagreement between a test and the
  code is logged in the sidecar and **the ledger decides**, never the code.

### Review gate R (every wave)
1. Build agent self-review: each ledger ID → evidence (test name / file:line).
2. `/code-review` (Claude Code, level per table).
3. Cross-vendor review (Codex; Claude `/code-review` when Codex wrote the code).
   Needs the branch pushed.
4. Findings fixed or recorded in the sidecar; PR description cites ledger IDs
   and the MCP baseline `2026-07-28`.

## 3. Kickoff prompt (per wave and lane)

```text
ROLE: Code Agent for Anticharon, sprint "Ecosystem Ergonomics" (v0.6.0 Beta).
WAVE: W{n} "{name}" — LANE: {build | test | review} — PHASE: {design | build | review}
MODEL: {model}/{effort}

READ FIRST, in order:
1. AGENTS.md (Rules 3, 6, 8, 11, 12 especially)
2. docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md — ledger IDs: {IDs}
3. docs/plans/ecosystem-ergonomics/ISSUES_DRAFT.md — issues {#…}
4. Sidecar: <main-checkout>/.local/docs/plans/ecosystem-ergonomics/handoffs/WAVE-{n}.md
   (main checkout root = parent of `git rev-parse --path-format=absolute --git-common-dir`)

RULES
- Implement ONLY the listed IDs. Out-of-scope findings → sidecar "Findings".
- DECIDED ledger items are final. Contradiction or undecided point → STOP, ask.
- PO-live-test / spike items ({list}) → scaffolding only, then STOP.
- Test lane: do not read implementation code; tests/ and tests/fixtures/ only.
- Never: tag, push to main, run `-m live` unless told, add dependencies,
  write personal absolute paths.
- Spec first (Rule 3), CHANGELOG [Unreleased] (Rule 6), `uv run pytest` green
  before gate B/R, lint gate per .agents/skills/linting.

DO: phase {phase} only. At its gate, update the sidecar (Progress, Done table,
Open questions, Findings, Verify, Next model) and print the same summary. STOP.
```

Continuation line after any gate or quota reset:

```text
Read the WAVE-{n} sidecar and the ledger IDs it cites. You are {model}/{effort}
for W{n} {lane}/{phase}. Do that phase only, update the sidecar, stop at its gate.
```

## 4. Switching model / vendor

- **Claude Code:** read the sidecar, set model/effort (`/model` or the app's
  picker), send the continuation line.
- **Codex / Gemini:** same kickoff prompt plus `START AT: {phase}`; paste the
  sidecar content if the tool cannot see the local `.local/` (Codex cloud
  cannot — push the branch and paste). Gemini CLI: set its context file to
  `AGENTS.md`.
- **One vendor per lane per wave** (consistent style inside a branch).

## 5. Quota pacing (Claude Pro)

- Weekly limit is the constraint; 5-hour windows pace the day.
- Don't start a Build phase above ~80–85% of a 5-hour window.
- Record usage % before/after each phase in the sidecar to calibrate.
- If the weekly budget runs hot: reviews → Codex, docs/fixtures → Gemini,
  Opus → Sonnet.
