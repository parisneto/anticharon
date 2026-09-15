# Anticharon Project Backlog

This backlog tracks completed milestones, upcoming sprint priorities, and long-term architectural goals for the **Anticharon** OpenRouter price tracker, analytical engine, and Model Context Protocol (MCP) server.

---

## 🎯 Current Sprint (Ecosystem Expansion & Intelligence Engine)

- [ ] **Shortlist Resilience Eval Harness & EDD Gate (`anticharon eval` + MCP Tool/Prompt)**:
  - Implement zero-dependency shortlist resilience evaluation ([`docs/specs/pre-work/draft_eval_harness.md`](docs/specs/pre-work/draft_eval_harness.md)).
  - Dual-mode support:
    1. Automated CI / CLI runner (`anticharon eval`) asserting candidate shortlist adequacy (`is_adequate: bool`, diversity, maturity, alias risk).
    2. FastMCP tool (`eval_shortlist`) and agent prompt (`anticharon_eval_advisor`) enabling host agents (Hermes, Claude Desktop) on Day 1 to detect single-vendor monocultures, alias volatility (`:latest`, `:free`), and cold-start models (<15d old).
  - Add golden benchmark test matrix (`tests/fixtures/eval_test_matrix.json`) covering modern model families (Gemini 2.5, DeepSeek R1/V3, Llama 3.3, Claude 3.5).

- [ ] **Historical Trajectory Ingestion & Day 1 Cold-Start Bootstrapping (ADR 0002)**:
  - Implement unauthenticated OpenRouter frontend stats API ingestion (`/api/frontend/v1/stats/effective-pricing` with `shape=v7&range=1m` & canonical `permaslug`) as defined in [`docs/specs/adr/0002_internal_frontend_stats_api_for_historical_trajectories.md`](docs/specs/adr/0002_internal_frontend_stats_api_for_historical_trajectories.md).
  - Dual-tier storage architecture: compact sliding `history.csv` + granular multi-provider `fullhistory.csv`.
  - Immediate 30-day behavioral profile classification on Day 1 without waiting 30 days for cron accumulation.
  - Smart selective sync policy (on spike ≥ +20%, on stale >7d, or via `anticharon sync --full`).

- [ ] **Policy-Aware "Super Discovery" & ZDR Inflation Engine**:
  - Integrate Zero Data Retention (ZDR) and workspace privacy routing filters into discovery.
  - Detect when headline prices are driven by non-routable providers (e.g. Darkbloom at $0.15 vs real ZDR floor at $0.214, +42.7% to +180% inflation).
  - Multi-tier tokenized fallback search (e.g., when `qwen/qwen3.8-flash` has 0 routable ZDR endpoints, fall back to viable siblings like `qwen/qwen3.8-27b`).
  - FastMCP tool `anticharon_super_discovery` and CLI flag `--zdr --explain-inflation`.

- [ ] **Expose `calibrate` as an MCP Tool (`calibrate_token_weights`)**:
  - Expose the OpenRouter activity log parser directly as an MCP tool so orchestrators can calibrate agent token mixes (`weight_prompt` / `weight_completion`) on the fly from log snippets or paths.

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
