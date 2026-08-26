# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `anticharon calibrate <csv>` CLI command to ingest OpenRouter activity logs and automatically persist calibrated weights to configuration.
- Empirical validation and TraceLab context (UW TraceLab Claude Code traces at 99.63% in / 0.37% out matching author's 99.71% in / 0.29% out).
- Private staging structure `dev_bucket/` in `.gitignore` for private scratch files, prompts, and drafts.
- Formal specification lifecycle in `AGENTS.md` (`docs/specs/pre-work/` → `docs/specs/` → `docs/specs/backlog/` → archive to `dev_bucket/`).
- Plain Markdown Unicode math formatting rule (`→`, `≤`, `≥`, `×`, `±`, `≠`) across all documentation.
- Embedded official steampunk-futuristic logo in `README.md`.

### Changed
- Updated default baseline weights to calibrated operational ratio: 99.71% input / 0.29% output.
- Moved deferred MCP integration guide to `docs/specs/backlog/mcp_integration_v2.md`.
- Archived raw draft notes and exploratory pre-work files to `dev_bucket/`.

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
