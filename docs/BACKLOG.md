# Anticharon Project Backlog

This backlog tracks completed milestones, upcoming sprint priorities, and long-term architectural goals for the **Anticharon** OpenRouter price tracker, analytical engine, and Model Context Protocol (MCP) server.

---

## 🎯 Current Sprint (Public Release & Repository Preparation)

- [x] **GitHub Actions CI Automation (`.github/workflows/ci.yml`)**: Automated headless test runner on every Push and Pull Request using `uv run python tests/run_tests.py` and `anticharon test`.
- [x] **Open-Source License (`LICENSE`)**: Added standard MIT License file establishing copyright (`(c) 2026 Páris Piedade Neto`) and liability protection.
- [x] **Issue & Pull Request Templates**:
  - `.github/ISSUE_TEMPLATE/bug_report.md` (structured price drift & execution bugs).
  - `.github/ISSUE_TEMPLATE/feature_request.md` (candidate models, discovery filters).
  - `.github/PULL_REQUEST_TEMPLATE.md` (test verification checklist).
- [x] **Public README Community Section**: Added "Contributing & Community" guide pointing contributors to Issues, PRs, and test suites.
- [x] **AGENTS.md Public Hardening**: Finalized agent operating guidelines with `.local/` staging rules and autonomous release triggers.

---

## 🚀 Priority Backlog (Sprint Next - Ecosystem Expansion & MCP Tooling)

- [ ] **Eval Harness & Eval-Driven Development (EDD) Gate (`anticharon eval` + MCP Tool/Prompt)**:
  - Implement zero-dependency shortlist resilience evaluation ([`docs/specs/pre-work/draft_eval_harness.md`](docs/specs/pre-work/draft_eval_harness.md)).
  - Dual-mode support:
    1. Automated CI / CLI runner (`anticharon eval`) asserting candidate shortlist adequacy (`is_adequate: bool`).
    2. FastMCP tool (`eval_shortlist`) and agent prompt (`anticharon_eval_advisor`) enabling host agents (Hermes, Open Claw) on Day 1 to detect single-vendor monocultures, alias volatility (`:latest`, `:free`), and cold-start models (<15d old).
  - Add golden benchmark test matrix (`tests/fixtures/eval_test_matrix.json`) covering modern model families (Gemini 2.5, DeepSeek R1/V3, Llama 3.3, Claude 3.5).
- [ ] **Expose `calibrate` as an MCP Tool (`calibrate_token_weights`)**:
  - Expose the OpenRouter activity log parser directly as an MCP tool so orchestrators (Hermes, Claude Desktop, Cursor) can calibrate agent token mixes (`weight_prompt` / `weight_completion`) on the fly.
- [ ] **Universal One-Way Shortlist Importers**:
  - Expand beyond Hermes to support one-way import of model slugs from other agent orchestrator configs and routing proxies (e.g. LiteLLM `config.yaml`, OpenRouter curated collections/rankings, Claude Code, and Cursor model definitions) into Anticharon's `shortlist.json`.
  - Always strictly one-way (source is read-only; writes exclusively to `shortlist.json`).
- [ ] **Interactive CLI Shortlist Picker**:
  - Add interactive multi-select TUI menu (`anticharon model select`) for selecting candidate models from discovery directly into the shortlist.
- [ ] **Extended Latency & Quality Metadata**:
  - Ingest Berkeley Function Calling Leaderboard (BFCL) scores and median OpenRouter generation latency when available in API payloads to display alongside price-per-1M tokens.
- [ ] **Model Metadata Storage & Multi-Dimensional Comparator Tool (`anticharon model compare`)**:
  - Ingest and persist structured model metadata from OpenRouter (`knowledge_cutoff`, `context_length`, `max_completion_tokens`, `architecture.modality`, `architecture.input_modalities`, `architecture.output_modalities`, `created`, `supported_parameters`, `reasoning.supported_efforts`) alongside pricing.
  - Transform candidate model discovery from a simple slug grep into a rich comparative helper tool allowing users and agents to filter models by context size, release recency, multimodal capabilities, and price efficiency.

---

## 🔮 Future Horizon (Ideas & Evaluation)

- [ ] **SQLite Historical Time-Series**:
  - Optional SQLite persistence engine for multi-year price trajectory analysis with sub-millisecond range queries.
- [ ] **Webhook & Notification Alerts**:
  - Discord/Telegram/Slack webhook dispatch when a monitored model exceeds the 20% spike threshold.
- [ ] **Zero-Disk Ephemeral Mode**:
  - Stateless execution mode for strictly sandboxed, non-persistent container runs.

---

## ✅ Completed Milestones

### Milestone 1: Core Pricing Engine (v0.1.0)
- [x] OpenRouter API client with 10s hard timeout and graceful offline fallback.
- [x] Weighted blended pricing formula ($P_{\text{blended}} = w_{\text{in}} P_{\text{in}} + w_{\text{out}} P_{\text{out}}$).
- [x] Compact 7-day sliding window CSV storage (`data/history.csv`) with cold-start padding.
- [x] Threshold-based price volatility alerts (Spike $\ge +20\%$, Drop $\le -10\%$, Alternative Cheaper $\ge 15\%$).
- [x] Zero-dependency test runner (`tests/run_tests.py`) and CLI self-test (`anticharon test`).

### Milestone 2: Activity Log Calibration & Analytics (v0.2.0 - v0.3.0)
- [x] OpenRouter activity log parser (`anticharon calibrate`) calculating exact empirical token mixes.
- [x] TUI ASCII price spectrum chart.
- [x] Model management CLI (`anticharon model add/remove/list/discover`).
- [x] 30-day historical intelligence engine with 5 behavioral profile badges (`🛡️ STABLE`, `📉 DISCOUNTED`, `⚠️ VOLATILE`, `🌅 SUNSETTING`, `🚨 PROMO_ENDED`).
- [x] Self-describing Agent-to-Agent (A2A) schema with `llms.txt` standard.

### Milestone 3: Model Context Protocol (MCP) Server (v0.4.0)
- [x] FastMCP stdio server architecture (`anticharon mcp`).
- [x] Strict stdio isolation (all human formatting routed to stderr; pure JSON-RPC on stdout).
- [x] 4 MCP Tools (`check_prices`, `get_model_history`, `discover_models`, `import_hermes_models`).
- [x] 3 MCP Resources (`anticharon://llms.txt`, `anticharon://shortlist`, `anticharon://profiles`).
- [x] 5 MCP Prompts (daily briefing, alternative finding, volatility auditing, family discovery, Gemini 3.7 vs 3.8 case study).
- [x] MCP Inspector test launcher (`scripts/inspect_mcp.sh`) and Cursor IDE integration.
