# Wave 1 VM verification (AC-1, AC-2)

Manual verification on the Hermes VM, 2026-10-02. Scope: Wave 1 only (EH-1, EH-2).
Evaluated revision: `9683b66`, installed with
`uv tool install --force git+https://github.com/parisneto/anticharon.git@codex/history-analytics-identity-sprint`.
The package version string stays `0.6.1`; the install log's commit ID identifies the build.
Paths below are sanitized to `~/.anticharon/`.

## Build identification

`anticharon history --json` emitted `observation_count`, `classification_reason`, and
`current_price_source`, which the released 0.6.1 build does not.

## AC-1 — effective-history maturity

- Five shortlisted models each reported `observation_count: 29` and
  `classification_reason: "29 distinct observed days ≥ 14 required for classification."`
- `current_price_source` was `quote`: no stored observation was dated today, so the
  exported price was the latest point (expected before the next `run`).
- Not covered here: an insufficient-history or gapped case on the VM (covered by
  `tests/test_analytics.py`).

## AC-2 — Hermes persistence and idempotence

1. Already-persisted shortlist: two consecutive `anticharon model sync` runs both reported
   `SHORTLIST_UNCHANGED`. `model list --json` showed `source: hermes` and `order` 0–5 on
   all six entries and exactly one `is_default: true` (`openai/gpt-5.6-luna`).
2. Preserved pre-fix backup restored over `~/.anticharon/shortlist.json` (the previous file
   kept alongside). The backup stores `shortlist` as a flat list of six model-slug strings
   with no `source` or `order`. The first `model sync` reported `SHORTLIST_UPDATED` (the
   flat list was rewritten with explicit metadata for the same six-model sequence); the
   second reported `SHORTLIST_UNCHANGED`. Same single default.

Limits: No `HERMES_DIVERGENT` or `NO_DEFAULT` message appeared in any output. Manual-entry
retention, manual-default preference, and authoritative removal were not exercised on the
VM (covered by `tests/test_hermes_ownership.py`).
