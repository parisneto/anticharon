# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
