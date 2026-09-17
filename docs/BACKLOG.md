# Anticharon Project Backlog

This backlog tracks completed milestones, upcoming sprint priorities, and long-term architectural goals for the **Anticharon** OpenRouter price tracker, analytical engine, and Model Context Protocol (MCP) server.

---

## 🎯 Current Sprint (Ecosystem Expansion & Intelligence Engine)

- [ ] **Repository-wide behavioral Ruff cleanup (deferred from PE2-010, approved 2026-09-17):** `ruff check src tests` retains 39 pre-existing findings across five behavioral rule codes that PE2-010's human sign-off explicitly forbade autofixing in the pricing-engine-v2 branch, since each requires a dedicated regression test to confirm no behavior change (out of scope for a minimal-change pricing release): `BLE001` (24, blind `except Exception`), `B023` (8, loop-variable closure binding), `S110`/`S112` (4 + 1, silent `try/except/pass` and `try/except/continue`), `PLW1510` (2, `subprocess.run` without explicit `check=`). See `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#pe2-010` for the sign-off and full finding history, and `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`'s Deferred section for the pre-existing broader (251-finding, all-rule) repository-wide Ruff cleanup candidate this is a named subset of.

- [ ] **Provider-granular historical persistence (deferred from PE2-004, approved 2026-09-17):** `PLAN.md`'s original design called for a per-model, *per-provider* daily time series (date, provider, effective price, listed price, cache-hit rate, token share). Human sign-off approved narrowing to the shipped single collapsed cheapest-price-per-day observation (`effective_prices.json`), since no current downstream consumer needs provider-level history. Revisit as its own initiative if a real feature needs it — see `docs/plans/pricing-engine-v2/PLAN.md`'s "Scope correction" note under "Storage architecture," `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`'s Deferred section, and `docs/specs/adr/0002_internal_frontend_stats_api_for_historical_trajectories.md`'s amendment for the full reconciliation. When picked up, it would unlock provider-routing features against OpenRouter's own API surface: price ceilings (`max_price`), performance sorting (`sort: "throughput"` / `:nitro`), and privacy enforcement (`data_collection: "allow" | "deny"`, `enforce_distillable_text`) — see [OpenRouter provider-selection docs](https://openrouter.ai/docs/guides/routing/provider-selection), [API reference](https://openrouter.ai/docs/api_reference/parameters), [service tiers](https://openrouter.ai/docs/guides/features/service-tiers).

- [ ] **Shortlist Resilience Eval Harness & EDD Gate (`anticharon eval` + MCP Tool/Prompt)**:
  - Implement zero-dependency shortlist resilience evaluation ([`docs/specs/pre-work/draft_eval_harness.md`](docs/specs/pre-work/draft_eval_harness.md)).
  - Dual-mode support:
    1. Automated CI / CLI runner (`anticharon eval`) asserting candidate shortlist adequacy (`is_adequate: bool`, diversity, maturity, alias risk).
    2. FastMCP tool (`eval_shortlist`) and agent prompt (`anticharon_eval_advisor`) enabling host agents (Hermes, Claude Desktop) on Day 1 to detect single-vendor monocultures, alias volatility (`:latest`, `:free`), and cold-start models (<15d old).
  - Add golden benchmark test matrix (`tests/fixtures/eval_test_matrix.json`) covering modern model families (Gemini 2.5, DeepSeek R1/V3, Llama 3.3, Claude 3.5).

- [ ] **Update default cache-hit-rate using TraceLab's cache breakdown**:
  - TraceLab's dataset (Total input 114.2B / Cached-read 109.2B / Append 5.01B / Output 391.8M) implies a ~95.3% cache-hit-rate — materially higher than the current interim default (~76.4%, pooled from only two personal `docs/sample/` log exports).
  - Update `DEFAULT_CACHE_HIT_RATE`/`DEFAULT_CONFIG` in `config.py`, reconcile `config/shortlist.example.json` to match exactly (currently off by ~0.00003 from `config.py`'s own default — separate small pre-existing drift, fix both together), and extend the README's "Backed by 114 Billion Tokens" TraceLab table with the cache-dimension row. Full computed numbers in [`docs/plans/pricing-engine-v2/PLAN.md`](docs/plans/pricing-engine-v2/PLAN.md) (Deferred section).

- [ ] **Pareto cutoff on provider token share before per-provider work**:
  - Long-tail providers with negligible token share (e.g. `deepseek/deepseek-v4.1-flash` has 12+ providers, but the top 3 already cover ~70% of daily volume) add cost to per-provider operations (live ZDR checks, weighted effective-price averaging) without materially changing the result.
  - Proposal: cut off providers once cumulative token share exceeds ~80% (configurable), skipping the remainder for these purposes.
  - **Needs verification first**: confirm whether `token_share`/similar is a clean field in the `effective-pricing` or `/stats/endpoint` raw JSON responses, or whether it must be derived from something like relative `request_count` across a model's endpoints.

- [ ] **Expose `calibrate` as an MCP Tool (`calibrate_token_weights`)**:
  - Expose the OpenRouter activity log parser directly as an MCP tool so orchestrators can calibrate agent token mixes (`weight_uncached_prompt` / `weight_cached_prompt` / `weight_completion`) on the fly from log snippets or paths.

- [ ] **Universal One-Way Shortlist Importers**:
  - Expand beyond Hermes to support one-way import of model slugs from other agent orchestrator configs and routing proxies (e.g. LiteLLM `config.yaml`, OpenRouter curated collections/rankings, Claude Code, and Cursor model definitions) into Anticharon's `shortlist.json`.
  - Strictly one-way read-only ingestion (external source is read-only; writes exclusively to `shortlist.json`).

- [ ] **Model Metadata Storage & Multi-Dimensional Comparator Tool (`anticharon model compare`)**:
  - Ingest and persist structured model metadata from OpenRouter (`context_length`, `max_completion_tokens`, `architecture.modality`, `supported_parameters`, `reasoning.supported_efforts`).
  - Enable multi-dimensional model comparison across context window, modality, price-per-1M, and provider depth.

- [ ] **Interactive CLI Shortlist Picker (`anticharon model select`)**:
  - Add interactive multi-select TUI menu for selecting candidate models from discovery directly into the shortlist.

---

## 🔮 Future Horizon (Ideas & Evaluation)

- [ ] **Extended Latency & Quality Metadata**:
  - Ingest Berkeley Function Calling Leaderboard (BFCL) scores and median OpenRouter generation latency when available in API payloads to display alongside price-per-1M tokens.
- [ ] **SQLite Historical Time-Series**:
  - Optional SQLite persistence engine for multi-year price trajectory analysis with sub-millisecond range queries.
- [ ] **Webhook & Notification Alerts**:
  - Discord/Telegram/Slack webhook dispatch when a monitored model exceeds the 20% spike threshold.
- [ ] **Zero-Disk Ephemeral Mode**:
  - Stateless execution mode for strictly sandboxed, non-persistent container runs.

---

## ✅ Completed Milestones

### Milestone 5: Pricing Engine v2 — Cache-Aware + Provider-Routable Pricing + 28-Day Backfill (v0.5.0)
- [x] Unifies three prior threads into one initiative — see [`docs/plans/pricing-engine-v2/`](docs/plans/pricing-engine-v2/) (`EXECUTION_CONTRACT.md`, `PLAN.md`, `ADR_CANDIDATE_TOKENS_CACHED.md`) for the full plan and evidence.
- [x] Cache-aware 3-component blended pricing (`tokens_cached` was never read from activity logs, overestimating real cost by 55–75% for cache-heavy agents), validated against 5 golden cases.
- [x] Provider-routable pricing via the real ZDR signal (`provider_info.dataPolicy.retainsPrompts`, live-verified — not the public `/endpoints` call's `status` field, which was initially assumed but doesn't carry it on an unauthenticated request). Surfaced via CLI flag `--zdr`.
- [x] The three-price model (advertised / effective / policy) as distinct, never-collapsed numbers everywhere a price is shown.
- [x] 28-day historical backfill on cold start (internal effective-pricing route with `range=1m`, live-verified required for ~30 days vs. the ~8-day default) replacing fabricated flat-padding with real observations; dual storage (`history.csv` compact summary + new granular `effective_prices.json` store).
- [x] Same-day-rerun bug fixed: `d1..d30`/MA columns derived fresh from dated observations each sync instead of shifted per run.
- [x] Elapsed-days `NEWLY_TRACKED` analytics threshold (`min_tracking_days_for_profile`), nullable history slots throughout.
- [x] Test suite matured to `pytest` as part of this initiative (`tests/run_tests.py` retired outright as the CI gate, per `AGENTS.md` Rule 8).

### Milestone 4: Public Release, Community Hardening & Ergonomics (v0.4.1 - v0.4.3)
- [x] GitHub Actions CI Automation (`.github/workflows/ci.yml`) on Python 3.12.
- [x] Open-source MIT License (`LICENSE`) and community issue/PR templates (`bug_report.md`, `feature_request.md`, `PULL_REQUEST_TEMPLATE.md`).
- [x] Diagnostic suite telemetry (`anticharon test` platform, architecture, paths).
- [x] TraceLab empirical comparison & narrative refinement in docs and specs.
- [x] Ergonomic `anticharon help` subcommand with target routing (`help run`, `help model discover`, etc.).
- [x] One-way Hermes model import naming (`import_hermes_models` / `model import-hermes`).

### Milestone 3: Model Context Protocol (MCP) Server (v0.4.0)
- [x] FastMCP stdio server architecture (`anticharon mcp`).
- [x] Strict stdio isolation (all human formatting routed to stderr; pure JSON-RPC on stdout).
- [x] 4 MCP Tools (`check_prices`, `get_model_history`, `discover_models`, `import_hermes_models`).
- [x] 3 MCP Resources (`anticharon://llms.txt`, `anticharon://shortlist`, `anticharon://profiles`).
- [x] 5 MCP Prompts (daily briefing, alternative finding, volatility auditing, family discovery, Gemini 3.7 vs 3.8 case study).
- [x] MCP Inspector test launcher (`scripts/inspect_mcp.sh`) and Cursor IDE integration.

### Milestone 2: Activity Log Calibration & Analytics (v0.2.0 - v0.3.0)
- [x] OpenRouter activity log parser (`anticharon calibrate`) calculating exact empirical token mixes.
- [x] TUI ASCII price spectrum chart.
- [x] Model management CLI (`anticharon model add/remove/list/discover`).
- [x] 30-day historical intelligence engine with 7 behavioral profile badges (`🛡️ STABLE`, `📉 DISCOUNTED`, `⚡ VOLATILE`, `⚠️ SUNSETTING`, `📈 PROMO_ENDED`, `🐌 CREEPING_INFLATION`, `🌱 NEWLY_TRACKED`).
- [x] Self-describing Agent-to-Agent (A2A) schema with `llms.txt` standard.

### Milestone 1: Core Pricing Engine (v0.1.0)
- [x] OpenRouter API client with 10s hard timeout and graceful offline fallback.
- [x] Weighted blended pricing formula (P_blended = w_in × P_in + w_out × P_out).
- [x] Compact 7-day sliding window CSV storage (`data/history.csv`) with cold-start padding.
- [x] Threshold-based price volatility alerts (Spike ≥ +20%, Drop ≤ -10%, Alternative Cheaper ≥ 15%).
- [x] Zero-dependency test runner (`tests/run_tests.py`) and CLI self-test (`anticharon test`).
