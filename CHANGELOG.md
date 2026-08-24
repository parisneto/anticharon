# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
