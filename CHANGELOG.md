# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.2] - 2026-09-04

### Added
- **GitHub Actions CI Pipeline (`.github/workflows/ci.yml`):**
  - Automated continuous integration runner testing pushes and pull requests across Python 3.12 with `tests/run_tests.py` and `anticharon test`.
- **GitHub Community Templates:**
  - Added `.github/ISSUE_TEMPLATE/bug_report.md` with environment diagnostic instructions.
  - Added `.github/ISSUE_TEMPLATE/feature_request.md` for candidate model and tool requests.
  - Added `.github/PULL_REQUEST_TEMPLATE.md` with verification quality checklist.
- **Environment Telemetry in Diagnostic Suite (`anticharon test`):**
  - Added system platform, OS release, CPU architecture, Python binary location, data directory, and config path to both human terminal and `--json` diagnostic outputs.

### Changed
- **Empirical Research Storytelling & TraceLab Citations:**
  - Corrected paper title to *"TraceLab: Characterizing Coding Agent Workloads for LLM Serving"*, updated UW SyFi blog/demo/GitHub links, and documented the 114.2B input vs 391.8M output token dataset (291.5 : 1 ratio).
  - Added comparative narrative and delta breakdown in `README.md` and `docs/specs/spec_v1_anticharon.md` highlighting how the academic dataset mirrors Anticharon's 99.71% in / 0.29% out baseline within 0.05% (-0.0005).
- **Public Backlog & License Cleanliness:**
  - Removed references to local zero-cost models (Ollama) from backlog, clarifying focus on remote orchestrator configs (LiteLLM, OpenRouter collections, Claude Code).
  - Standardized author name to `Páris Piedade Neto` across `LICENSE`, `pyproject.toml`, and documentation.

## [0.4.1] - 2026-09-04

### Changed
- **MCP Tool Rename (`sync_hermes_models` → `import_hermes_models`):**
  - Renamed tool to `import_hermes_models` to clearly communicate one-way ingestion into Anticharon's shortlist.
  - Set default `dry_run=True` for safe-by-default preview mode in MCP tool invocations.
  - Added directional response metadata: `"direction": "hermes→anticharon"` and `"hermes_untouched": true`.
  - Added explicit status notices clarifying preview vs shortlist update state.
- **CLI Model Subcommands (`src/anticharon/cli.py`):**
  - Added `anticharon model import-hermes` as the primary command (retaining `sync` as an alias).
  - Terminal output now explicitly prints `🔒 Hermes configuration is untouched (read-only)`.
- **Public Repository Hardening & Spec Lifecycle:**
  - Migrated private developer drafts and deployment scripts from `dev_bucket/` to `.local/` (strictly ignored by git).
  - Archived exploratory notes (`diagnostic_v1_mcp_architecture.md`, `mcp_prompts_v2.md`, `model_discovery.md`) to `.local/docs/specs/`.
  - Created public sprint roadmap in `docs/BACKLOG.md`.
  - Updated `AGENTS.md` Rule 2 and Section 2 directory layout.

### Added
- **Official Open-Source License:**
  - Added `LICENSE` (MIT License, Copyright (c) 2026 Paris Piedade Neto) at repository root.
- **Private GitHub Release Playbook (`.local/docs/github_release_and_pr_playbook.md`):**
  - Added comprehensive guide for solo developers on free personal accounts, covering GitHub Actions CI, step-by-step PR reviews, and SemVer release management.
- **MCP Prompt Suite Extensions:**
  - Added `family_upgrade_discover`, `daily_cost_briefing`, and `budget_optimization_audit` prompt templates.
  - Added `src/anticharon/__main__.py` entrypoint and `scripts/inspect_mcp.sh` helper.

## [0.4.0] - 2026-09-03

### Added
- **Model Context Protocol (MCP) Server Architecture (`src/anticharon/mcp.py`):**
  - Native stdio MCP server implementation using FastMCP (`mcp>=1.3.0`).
  - Strict stdio hygiene: `stdout` reserved exclusively for JSON-RPC 2.0 frames; all diagnostic logs, banners, and non-fatal fallback notices routed safely to `stderr` to prevent client disconnection.
  - Subcommand `anticharon mcp` with `--transport stdio` support.
  - Exposes 4 specialized MCP tools:
    - `check_prices`: Live pricing, weighted blended costs, 7-day MA, volatility alerts, and 30-day intelligence profiles.
    - `get_model_history`: 30-day temporal breakdown, statistical CV%, directional trend sparklines, and profile recommendations (JSON or raw CSV).
    - `discover_models`: Live multi-criteria catalog search across ~417+ models with user-calibrated blended pricing.
    - `sync_hermes_models`: Bi-directional synchronization with Hermes `model.default` and `fallback_providers`.
  - Exposes 3 native MCP resources:
    - `anticharon://llms.txt`: Agent-to-Agent discovery briefing and schema documentation.
    - `anticharon://history.csv`: Raw 30-day sliding history data table.
    - `anticharon://shortlist.json`: Active configuration and calibrated weights.
  - Exposes 2 MCP prompt templates:
    - `cost_spike_triage`: Prompt template guiding agents to analyze `PRICE_SPIKE` / `PROMO_ENDED` alerts.
    - `model_migration_advisor`: Prompt template guiding model migration from `SUNSETTING` models.
- **XDG Base Directory Compliance (`src/anticharon/config.py`):**
  - Added support for `$XDG_CONFIG_HOME/anticharon/shortlist.json` (`~/.config/anticharon/`) and `$XDG_DATA_HOME/anticharon/` (`~/.local/share/anticharon/`).
  - Added graceful fallback to `/tmp/anticharon` if running in strictly read-only sandboxes.
- **Architecture Decision Record (ADR 0001):**
  - Documented unified single-repository architecture, stdio isolation, XDG hierarchy, and in-band `_hints` design in `docs/specs/adr/0001_mcp_unified_repo_and_stdio_architecture.md`.
- **MCP Self-Test & Diagnostic Suite (`anticharon test` & `tests/run_tests.py`):**
  - Step 7 in `anticharon test` validates MCP server tool registration, resource loading, and async runtime.
  - Added comprehensive MCP automated test suite in `tests/run_tests.py` (11/11 tests passing in <0.4s).
- **Comprehensive Documentation & Guide Updates:**
  - Synchronized official specification `docs/specs/spec_v1_anticharon.md` with Section 10 MCP Server Architecture.
  - Promoted and retired `docs/specs/backlog/mcp_integration_v2.md`.
  - Updated `README.md` and `llms.txt` with Claude Desktop and Hermes Agent MCP configuration examples and `uvx` installation guides.

### Added
- **Self-Describing A2A JSON Schema Keys:**
  - Added `data_source` (`"live_api"` or `"cached_history"`) to unambiguously declare data provenance.
  - Added `api_offline_fallback` boolean, preventing autonomous LLM agents (such as Hermes) from confusing HTTP cache fallbacks with model `fallback_providers`.
  - Added CLI flag `--hints` to include an in-band `_hints` dictionary explaining payload keys directly inside JSON responses.
  - Preserved `fallback` boolean as a backward-compatible alias.
- **A2A JSON Schema & Field Glossary in `llms.txt`:** Added dedicated glossary section detailing field definitions, cache fallback boundaries, and Hermes integration models count.

## [0.3.1] - 2026-09-02

### Fixed
- **Wheel Package Resource Bundling for `llms.txt`:** Bundled `llms.txt` inside `src/anticharon/` and updated `anticharon info` to load via Python's standard `importlib.resources`. This ensures the complete Agent-to-Agent briefing is always found in isolated `uv tool install` and `pip` environments regardless of working directory.
- **Auto-Seeding of `~/.anticharon/llms.txt`:** Automatically writes or syncs `llms.txt` into the user's config directory for direct agent inspection.

## [0.3.0] - 2026-09-02

### Added
- **Historical Analytical Intelligence & Model Pricing Profiles (`src/anticharon/analytics.py`):**
  - Evaluates 30-day temporal dispersion across 9 historical slots (`d1..d7, d15, d30`) and current prices.
  - Classifies shortlisted models into 7 deterministic profiles: `🛡️ STABLE`, `📈 PROMO_ENDED`, `⚠️ SUNSETTING`, `⚡ VOLATILE`, `🏷️ DISCOUNTED`, `🐌 CREEPING_INFLATION`, and `🌱 NEWLY_TRACKED`.
  - Sibling alternative detection (`find_sibling_alternatives`) flagging newer version models in the same family available at equal or lower cost (e.g. Gemini 3.8 vs 3.7).
  - Compact trajectory trend sparklines (e.g. `$0.38 ──↑ $0.76 (+100.0%)`).
- **Dedicated Subcommand `anticharon history`:**
  - Audits 30-day temporal analytics, statistical volatility ($CV\%$), min/max spreads, and actionable recommendations.
  - Option `--csv` to dump the raw 30-day `history.csv` table directly to stdout for Unix piping.
- **CLI Options `--profile` and `--history-csv`:** Added to `anticharon run`, `anticharon check`, and default invocation.
- **Machine-Readable Pre-Processed Analytics in `--json`:** Adds structured `.analytics` object containing profile, badges, variance, trend direction, sparklines, and sibling alternatives so agents (Hermes) receive pre-digested intelligence.
- **Agent-to-Agent (A2A) Discovery Standard (`llms.txt`):**
  - Authoritative `llms.txt` specification at repository root.
  - New `anticharon info [--json]` CLI command streaming operational briefing directly to stdout for LLM agent discovery.
- **Comprehensive Test Suite Expansion:** 10/10 automated tests covering family parsing, sibling alternatives, profiles classification, history export, and `llms.txt`.

## [0.2.1] - 2026-09-02

### Added
- **Hermes Agent Auto-Detection & Two-Tier Model Synchronization (`src/anticharon/hermes.py`):**
  - Tier 1 CLI detection: executes `hermes config get model` and `hermes config get fallback_providers` directly if `hermes` is on `$PATH`.
  - Tier 2 Stream-Grep parser: line-by-line streaming extraction of active `default:` model and OpenRouter `fallback_providers:` without `pyyaml`, constant memory footprint, and zero secret leakage.
  - Model ordering guarantee: Hermes default model is pinned to `shortlist[0]` (`★ [DEFAULT]`), driving `BEST_OPTION_CHANGED` alerts.
  - Upgrade resilience: automatically recreates `~/.anticharon/shortlist.json` from Hermes on fresh VM or post-upgrade installs.
- **Dedicated CLI Subcommand `anticharon model sync`:** Explicit manual or programmatic synchronization with `--hermes-config`, `--dry-run`, and `--json` support, plus interactive prompt if run in an interactive terminal.
- **CLI Options `--hermes-config` and `--no-hermes`:** Added across `anticharon run`, `anticharon check`, and `anticharon test`.
- **Prominent Terminal & JSON Warning Banners:** Displays a big bold warning in terminal and consistent JSON payload (`"hermes_integration": {"detected": false, "warning": "..."}`) when Hermes configuration is missing in non-suppressed mode.
- **Diagnostics Step in `anticharon test`:** Probes Hermes configuration and reports detection status.
- **Repository-Relative Path Standard (`Rule 10` in `AGENTS.md`):** Explicit agent operating guideline prohibiting hardcoded host paths (`/Users/...`, `file:///...`) and enforcing clean repository-relative links across all markdown, code comments, and specifications.

### Changed
- Integrated Hermes pre-flight auto-synchronization into `run_tracker`, preserving user token weights while syncing newly active models.
- Sanitized absolute local filesystem paths in documentation and pre-work diagnostics (`AGENTS.md`, `docs/specs/pre-work/diagnostic_v1_mcp_architecture.md`) to standard relative Markdown paths for privacy and GitHub portability.

## [0.2.0] - 2026-08-26

### Added
- **Model Discovery Engine (`anticharon model discover`):** Query live OpenRouter catalog (~417+ models) with multi-criteria search, `--promo` filter (discounted and `:free` models), `--modality text` filtering, and price threshold expressions (`--filter "price < 10"`, `--max-input-price`, etc.).
- **Model Shortlist Management (`anticharon model add / remove / list`):** Command-line model management with live catalog validation, duplicate prevention, and `--dry-run` inspection.
- **TUI ASCII Price Spectrum Chart:** Proportional ASCII bar chart (`█`) in `run` and `check` outputs visualizing relative pricing distribution (`▲ Cheaper` to `▼ More Expensive`), badging `🏆 [BEST]` and `★ [DEFAULT]` models.
- `anticharon calibrate <csv>` CLI command to ingest OpenRouter activity logs and automatically persist calibrated weights to configuration.
- Empirical validation and TraceLab context (UW TraceLab Claude Code traces at 99.63% in / 0.37% out matching author's 99.71% in / 0.29% out).
- Live storage and config file paths displayed in CLI header output (`💾 Storage:` and `⚙️ Config:`).
- Private staging structure `dev_bucket/` in `.gitignore` for private scratch files, prompts, and deployment scripts.
- Semantic Versioning & Release Governance rule in `AGENTS.md`.

### Changed
- Streamlined calibration CLI into a single `anticharon calibrate` command with `--dry-run`.
- Updated default baseline weights to calibrated operational ratio: 99.71% input / 0.29% output.
- Cleaned up float serialization in CSV storage (`round(x, 6)`).
- Moved deferred MCP integration guide to `docs/specs/backlog/mcp_integration_v2.md`.

## [0.1.0] - 2026-08-24

### Added
- Initial project architecture and environment setup using `uv`.
- Dual-mode architecture specification: CLI runner with built-in `--test`, `--dry-run`, and deferred MCP server integration blueprint.
- Core math engine: weighted price per 1M tokens ($W_{in} = 0.9922, W_{out} = 0.0078$), 3-day and 7-day moving averages (`MA_3d`, `MA_7d`), and 30-day sliding window array.
- OpenRouter activity log parser (`calculate-prompt-mix`) to compute agent prompt/completion token mix from exported dashboard CSVs.
- Volatility alerts: `PRICE_SPIKE`, `PRICE_DROP`, and `BEST_OPTION_CHANGED`.
- Compact 1-line-per-model CSV storage (`history.csv`) with automatic cold-start replication.
- Resilient network error handling with 10-second request timeouts and fallback to local history cache.
- Strict agent rules defined in `AGENTS.md` and formal specification in `docs/specs/spec_v1_anticharon.md`.
- Zero-dependency validation test runner script `tests/run_tests.py`.
