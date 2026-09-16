# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-09-16

### Added
- **Project Test & Tooling Dependencies (`pyproject.toml`):**
  - Added `pytest` and `ruff` to project dependencies; `[tool.pytest.ini_options]` now sets `addopts = "-m 'not live'"` so the bare `uv run pytest` gate is deterministic by default (a pre-existing gap — it previously ran live network tests unless `-m "not live"` was passed manually).
- **Reference Fixtures & Documentation Assets:**
  - Added `docs/sample/openrouter_activity_2026-09-15.csv` empirical activity log sample, and real live-captured API-payload fixtures under `tests/fixtures/` (sanitized/trimmed to the fields actually consumed).
  - Added ZDR OpenRouter reference visual artifacts (`docs/images/ZDR example Qwen3.8/`).
- **Dev Tooling (`scripts/pick_random_test_models.py`):**
  - Draws a randomized, diverse set of real OpenRouter model slugs (newest/most-popular/cheapest/priciest/longest-context) for `@pytest.mark.live` tests instead of a fixed hardcoded pair.

### Changed — Pricing Engine v2 (cache-aware + provider-routable pricing + 28-day backfill)

See `docs/plans/pricing-engine-v2/` (`EXECUTION_CONTRACT.md`, `PLAN.md`, `ADR_CANDIDATE_TOKENS_CACHED.md`) for the full plan and evidence. The legacy 2-component gross pricing formula is **removed** as an independent downstream path everywhere it was used (`tracker.py`, `discovery.py`) — not kept behind a flag.

- **BREAKING: `current_price_1m` → `effective_price_1m`.** Renamed in the `history.csv` column header, the CLI `--json` output, and the `check_prices` MCP tool's return shape. No backward-compatibility shim (pre-launch, single-digit testers) — delete/regenerate a stale local `history.csv` from before this change.
- **BREAKING: `history.csv` values now mean something semantically different**, even where the file format stays readable — the blended price is now cache-aware and provider-routable rather than a flat 2-component estimate, and it's the *cheapest real endpoint's* price rather than always the bulk-catalog headline.
- **The Three-Price Model:** every price display/JSON output now surfaces `advertised_prompt_1m`/`advertised_completion_1m` (raw bulk-catalog headline, never blended, never an input to any calculation), `effective_price_1m` (3-component cache-aware blend against the cheapest real endpoint), and an optional `policy_price_1m`/`is_policy_routable` (restricted to Zero-Data-Retention-compliant endpoints when `--zdr`/`zdr_only` is active) as three deliberately distinct numbers — never collapsed into one (`ModelPrice.price: PricePoint`, `src/anticharon/models.py`).
- **Cache-aware blended formula** (`src/anticharon/pricing.py`, new module): `Price = (P_uncached × w_uncached) + (P_cache_read × w_cached) + (P_out × w_completion)`, validated against 5 independently-derived golden cases (`tests/test_golden_pricing.py`) proving the legacy formula overestimated cache-heavy cost by 55–75%.
- **Real ZDR data source correction (live-verified 2026-09-16):** the public `/models/{slug}/endpoints` call's `status` field does *not* carry ZDR-routability on an unauthenticated request — it reports `0`/routable for every provider regardless of real policy. The real, unauthenticated signal is `provider_info.dataPolicy.retainsPrompts` from the internal `GET /api/frontend/v1/stats/endpoint` route, which supersedes the public `/endpoints` call entirely for this project and also carries the same pricing fields already relied on.
- **New CLI flag `--zdr`** on `run`/`check`/`model discover` restricts the policy price to ZDR-compliant endpoints and emits a new `POLICY_UNROUTABLE` price warning (with `policy`/`excluded_providers`/`reason`) when none exist. `discover --zdr` performs one extra live policy check per candidate model still in the catalog after the sentinel-price guard below — opt-in and slower by design, not something the default browse pays for.
- **28-day historical backfill:** new granular `effective_prices.json` store (per-model `first_seen`/`last_synced`/daily `observations`), independently staleness-gated (default 24h) from `history.csv`'s per-run cadence. Backfilled from `GET /api/frontend/v1/stats/effective-pricing?...&range=1m` — **`range=1m` is required**; live-verified the bare/default call only returns ~8 days, not ~30 (undocumented publicly). Graceful degradation: a `~`-prefixed router alias (e.g. `~deepseek/deepseek-pro-latest`) returns an empty-but-200-OK payload (no fixed permaslug identity to have history against); a transient failure never overwrites previously accumulated real observations.
- **Same-day-rerun bug fixed:** `history.csv`'s `d1..d7/d15/d30` and `ma_3d`/`ma_7d` are now derived fresh from the granular store every sync instead of shifted by one slot per run — running `anticharon run` twice in one calendar day no longer corrupts the window (live-verified end-to-end).
- **Cache-aware 3-way calibration weights:** `anticharon calibrate` now persists `weight_uncached_prompt`/`weight_cached_prompt`/`weight_completion` (replacing the 2-way `weight_prompt`/`weight_completion`). Default config decomposes the existing TraceLab-cited 99.71%/0.29% split using an interim pooled cache-hit-rate (`0.766701`, from the two real activity-log samples in `docs/sample/` — flagged in `PLAN.md`'s Deferred section as needing a better documented source).
- **Elapsed-days analytics threshold:** `calculate_model_analytics` now gates `NEWLY_TRACKED` on elapsed calendar days since a model was first tracked (new `min_tracking_days_for_profile`, default 14) instead of slot identity/count — a model with real backfill gaps (e.g. only `d1` and `d15` populated) can still classify `STABLE`/`VOLATILE`/etc. once enough time has elapsed. History slots are nullable throughout (`Optional[float]`); missing observations are never fabricated.
- **Sentinel/negative-price guard** (`is_valid_listed_price`): OpenRouter meta-router models (`openrouter/auto`, `auto-beta`, `fusion`, `pareto-code`, `bodybuilder` — live-verified) list pricing as the raw sentinel `"-1"`, which the `× 1,000,000` conversion turned into a real-looking `-1,000,000.0/1M` that ranked as globally cheapest everywhere pricing is compared. Both the shortlist tracker and the full-catalog browse now skip any model with a negative listed price (zero/free is still valid).
- **Governance & tooling:** Rule 8 (`AGENTS.md`) evolved from zero-dependency testing to deterministic `pytest`-based testing; `tests/run_tests.py` retired outright as the CI gate (`uv run pytest` replaces it in `.github/workflows/ci.yml`, `README.md`, `.github/PULL_REQUEST_TEMPLATE.md`) — its coverage was ported into focused `tests/test_*.py` files, updated where behavior genuinely changed (schema, weights, thresholds) and marked `@pytest.mark.live` where it made real network calls. `anticharon test` (the user-facing diagnostic command) is unaffected.

## [0.4.3] - 2026-09-10

### Added
- **Ergonomic `help` Subcommand (`src/anticharon/cli.py`):**
  - Added native `anticharon help` subcommand displaying top-level help with exit code 0, resolving issue [#1](https://github.com/parisneto/anticharon/issues/1).
  - Added target subcommand help routing (e.g. `anticharon help run`, `anticharon help model`, and nested `anticharon help model discover`).
  - Added clean stderr error messaging and standard exit code 2 when an unknown help target is requested.
- **Automated Validation Suite Expansion (`tests/run_tests.py`):**
  - Added automated unit test (`test_cli_help_subcommand`) covering top-level help, subcommand help, nested subcommand help, and unknown target error routing (expanding test suite to 12/12 passing).

### Changed
- **CLI Specification Sync (`docs/specs/spec_v1_anticharon.md`):**
  - Documented the `anticharon help` command and nested target options in Section 7.

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
