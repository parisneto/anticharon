# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Hermes YAML fallback list dropped, destroying the synced shortlist (#4) (`src/anticharon/hermes.py`, `tracker.py`, `cli.py`, `mcp.py`, `tester.py`):**
  - `fetch_models_from_cli()` parsed `hermes config get fallback_providers` as JSON only, but the Hermes CLI emits a raw YAML list (`- provider: openrouter` / `  model: <slug>`). Every fallback was silently discarded and the function still returned a "successful" default-only result, which `sync_hermes_to_config()` then persisted — destructively shrinking a good multi-model shortlist to a single entry. The CLI tier now parses the YAML list form alongside the existing inline-JSON form.
  - `extract_models_from_file()` dropped the final fallback entry whenever the `fallback_providers:` YAML block was closed by a following top-level key (e.g. `logging:`) instead of EOF. The pending item is now flushed on any top-level key, exactly as the EOF path already did.
  - Detection now resolves to one of three named outcomes per source — `complete`, `incomplete`, `unavailable` — carried as a `detection` field on the payload (`unavailable` = no payload). `get_hermes_models()` falls through to the file tier when the CLI result is `incomplete`, not only when it is `unavailable`; a `complete` file result is authoritative, clears the incomplete CLI state and emits no warning. Source order (CLI → file) is never reversed.
  - `sync_hermes_to_config()` never overwrites a longer existing shortlist from an `incomplete` detection; a `complete` result remains authoritative and may legitimately shrink the shortlist.
  - When detection is `incomplete`, the existing shortlist is preserved and also used for the current tracking run, and a visible warning is surfaced in human CLI output, `--json` (`hermes_integration.warning`; `detection`/`warning` on `model sync`), and the `import_hermes_models` MCP payload.
  - `anticharon test` now reports `[WARN]` instead of an unqualified `[PASS]` when the detected Hermes model set diverges from the persisted shortlist or detection is incomplete, exposing `detection`, `shortlist_divergence` and `warning` in `--json`.
  - Spec updated: `docs/specs/spec_v1_anticharon.md` §6.2.
- **`anticharon check --zdr` broke the ASCII price spectrum chart (#3) (`src/anticharon/chart.py`):**
  - Under `--zdr` the tracker ranks the shortlist by ZDR *policy* price (a confirmed-unroutable model sorts last at rank `∞`), then handed that same list to `render_ascii_price_bar()`, which assumed input sorted by effective `price_1m` and derived its 100%-width scale from `prices[-1].price_1m`. With an unroutable-but-cheap model landing last, every ratio was computed against that tiny price — producing bars up to 8× `max_bar_width` (e.g. 64/128/256 blocks against a 32-block cap), destroying the triangle shape and overflowing the terminal.
  - The chart now sorts a local working copy by `price_1m` and scales off `max(price_1m)`, so it renders correctly for any input order. Bar widths are monotonically non-decreasing, no bar exceeds `max_bar_width`, and `🏆 [BEST]` badges the true lowest-effective-price model.
  - `tracker.py`'s ZDR ranking for the main list and `BEST_OPTION_CHANGED` is deliberately unchanged.
  - Spec updated: `docs/specs/spec_v1_anticharon.md` §3.2.

## [0.5.4] - 2026-09-20

### Fixed
- **`uv.lock` corrupted with a duplicate `dev-dependencies` table (#5):** `uv sync --frozen` failed with a TOML parse error (`duplicate key 'dev-dependencies' in table 'package'`) on every fresh clone, blocking AGENTS.md's own "Setup & Sync" workflow. Introduced in `6bf0ad8` (0.5.3 release) by hand-editing `uv.lock` instead of regenerating it via `uv lock`. Regenerated `uv.lock` from `pyproject.toml`; also corrects the `anticharon` package entry's stale `0.5.2` version stamp inside the lock file to match `0.5.3`.

## [0.5.3] - 2026-09-19

### Added
- **Pricing Engine v2:** Replaces flat-rate pricing with a 3-tier model (advertised, effective cache-aware, and Zero Data Retention rates) plus 28-day historical backfill.
- **Pre-Flight Release Audits:** Added Advisory Auditor agent ledger process with `pip-licenses`, `pip-audit`, `gitleaks`, and `git ls-files` exposure reviews.

### Fixed
- **PE2-001 — Effective and policy prices no longer collapse under `--zdr` (`src/anticharon/tracker.py`, `src/anticharon/models.py`):**
  - `ModelPrice.price_1m` (and the serialized `effective_price_1m` field in CLI `--json`/`check_prices` MCP output) is now ALWAYS the unconstrained effective price, never silently replaced by the policy-constrained price when `--zdr` is active. Previously, an active ZDR filter collapsed the two into one number under the `effective_price_1m` label — e.g. Luna's real effective price ($0.03267/1M) was reported as $0.06534/1M (its ZDR policy price) once `--zdr` was passed.
  - `ma_3d`/`ma_7d`/`delta_7d_pct`/`PRICE_SPIKE`/`PRICE_DROP` now always compare against the unconstrained effective price, matching the axis `effective_prices.json`'s historical observations are stored on (previously these silently switched to comparing the policy price against effective-price history under `--zdr` — an apples-to-oranges comparison).
  - A model with no ZDR-compliant endpoint at all is now excluded from being ranked "cheapest" and can no longer trigger `BEST_OPTION_CHANGED` under an active policy filter (previously an entirely unroutable model — e.g. a ZDR-blocked Qwen model — could be recommended as the best option, since sort/recommendation silently fell back to its unconstrained effective price).
  - Full evidence, root cause, and regression tests in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001`. Spec updated: `docs/specs/spec_v1_anticharon.md` §3.1 and §3.7 rule 3.
- **PE2-002 — Missing/partial pricing no longer becomes a fabricated `$0` endpoint (`src/anticharon/pricing.py`, `tracker.py`, `discovery.py`):**
  - `pricing.prompt`/`pricing.completion` are required fields on both the bulk catalog and each per-endpoint entry. A missing key, `null`, blank string, or non-numeric value previously defaulted to `0.0` (via `pricing.get("prompt", 0)`), indistinguishable from a genuine free model — letting a broken/partial endpoint win "cheapest" sorting and `BEST_OPTION_CHANGED` recommendations at a fabricated $0 price.
  - New `parse_required_price_1m()` returns `None` (not `0.0`) for missing/blank/malformed required fields; every call site now skips the model/endpoint entirely rather than pricing it at a fabricated `$0`. A genuine `"0"` (real free models) still parses correctly — live-verified every real free model explicitly lists `"0"` rather than omitting the key.
  - Also fixed a related bug this surfaced in `resolve_policy_pricing`: it gated policy-routability on whether the raw endpoint list was non-empty, not on whether any endpoint actually produced a usable price — so a policy check against only malformed endpoints was incorrectly reported as "confirmed unroutable" rather than "policy-unknown."
  - Full evidence, root cause, and regression tests in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-002`. Spec updated: `docs/specs/spec_v1_anticharon.md` §3.1a.
- **PE2-003 — Policy lookup failure is now policy-unknown, never confirmed noncompliance (`src/anticharon/tracker.py`, `discovery.py`, `cli.py`):**
  - `apply_zdr_filter()` (`model discover --zdr`) previously dropped a model entirely whenever its endpoint fetch returned no data — for any reason: timeout, HTTP error, malformed response, or genuinely zero endpoints — treating "we don't know" identically to "confirmed not ZDR-compliant." It now keeps such a model (routable-by-default, per the plan's explicit graceful-degradation rule) and names it in the returned warning.
  - Reconciles PE2-001's own remaining gap (flagged during independent review): ranking under `--zdr` (`run`/`check`) previously treated policy-unknown and confirmed-unroutable identically (both ranked last, `math.inf`, never recommendable). They are now distinct — policy-unknown ranks by the unconstrained effective price and *can* be recommended; only confirmed-unroutable (real endpoint data checked, none ZDR-compliant) ranks last.
  - New `PriceWarning` type `POLICY_UNKNOWN` surfaces this uncertainty explicitly wherever `POLICY_UNROUTABLE` already appears (CLI human output, `--json`, `check_prices` MCP output) — distinct from `POLICY_UNROUTABLE`, which is now reserved for confirmed noncompliance only.
  - Full evidence, root cause, and regression tests in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-003`. Spec updated: `docs/specs/spec_v1_anticharon.md` §3.2 and §3.7 (also corrects a stale §3.7 line left over from PE2-001's own fix, which had claimed the policy price replaces the effective price in `Delta_7d_Pct` — it never should have, per PE2-001's own resolution).

### Changed
- **PE2-004 — `effective_prices.json`'s planning docs formally narrowed to match the shipped schema (`docs/plans/pricing-engine-v2/PLAN.md`, `EXECUTION_CONTRACT.md`, `docs/specs/spec_v1_anticharon.md`):**
  - `PLAN.md`'s "Storage architecture" section originally described a per-model, *per-provider* daily time series (date, provider, effective price, listed price, cache-hit rate, token share). That was never implemented — the shipped store collapses every day to one cheapest-price observation per model, with no provider identity persisted. Rather than leaving the mismatch unresolved or silently rewriting history to pretend it was always the plan, this is now recorded explicitly as a deliberate scope decision: `EXECUTION_CONTRACT.md`'s actual Storage acceptance criteria never required provider-level persisted granularity, and no downstream calculation in this codebase currently needs it — building it speculatively would violate the Contract's own "concrete over general" Non-Goal.
  - `docs/specs/spec_v1_anticharon.md` §5.2's heading itself incorrectly said "per-model, per-provider daily observations" (the schema documented directly below it never matched that claim) — corrected.
  - Provider-granular historical persistence is now tracked as an explicit deferred backlog candidate in `EXECUTION_CONTRACT.md`, to be scoped against a real downstream consumer if one is ever proposed.
  - New regression test locks in the reduction rule as an approved decision, not an oversight: `tests/test_effective_pricing_backfill.py::test_reduce_to_daily_observations_provider_identity_is_intentionally_discarded`.
  - Full evidence and rationale in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-004`. **Flagged for user awareness:** this is a scope/design decision, not a mechanical bug fix — see this session's final report for the full trade-off if a future need for provider-level history emerges.

### Fixed
- **PE2-005 — Live backfill cross-validation canary now compares real, comparable listed prices (`src/anticharon/tracker.py`, `tests/test_effective_pricing_backfill.py`, `docs/plans/pricing-engine-v2/PLAN.md`):**
  - The original canary design assumed the internal effective-pricing route (`/stats/effective-pricing`) itself exposes a "listed" baseline distinct from its cache-weighted effective prices, and asserted a loose `cheapest_effective_input <= advertised_prompt_price × 1.5` — which could pass even after a substantial semantic drift between the two routes, and never actually compared like-for-like listed values as the plan intended. Live-verified 2026-09-17: that route has no raw listed-price field at all.
  - New `extract_endpoint_listed_prices_1m()` extracts each endpoint's own raw listed prompt price from `/stats/endpoint` (the route already used for policy/effective pricing elsewhere). The corrected canary asserts the bulk catalog's `advertised_prompt_1m` exactly matches at least one real endpoint's listed price (tight float-rounding tolerance, not a loose multiplier) — live-verified 2 of 7 endpoints matched for `openai/gpt-5.6-luna`.
  - Full evidence and rationale in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-005`. Plan corrected: `docs/plans/pricing-engine-v2/PLAN.md`'s "28-Day Backfill" section.

### Added
- **PE2-006 — Deterministic failure-path, realistic-fixture, and MCP/CLI three-price coverage (new `tests/test_network_failure_paths.py`; extended `tests/test_mcp.py`, `test_cli.py`, `test_effective_pricing_backfill.py`):**
  - `fetch_openrouter_models()` and `fetch_effective_pricing_history()` (previously only `fetch_endpoint_policy_pricing()`, from PE2-003) now have direct, deterministic, mocked coverage of every distinct failure mode — timeout, connection error, HTTP error, malformed JSON, wrong response shape — proving each degrades to its documented empty value (`{}`) rather than raising or returning partial garbage.
  - New sanitized fixture `tests/fixtures/openrouter_effective_pricing_gpt-5.6-luna_trimmed.json` (a real, live-captured, trimmed-to-5-days `/stats/effective-pricing` response) plus a deterministic test parsing it through `_reduce_to_daily_observations` — backfill parsing was previously exercised only against synthetic dictionaries, so a genuine payload-shape regression in this route could pass the offline suite undetected.
  - `tests/test_mcp.py` was entirely `@pytest.mark.live` and never deterministically asserted the three-price (advertised/effective/policy) payload. Two new deterministic (mocked, no network) tests exercise `check_prices(zdr_only=True)` through the actual MCP tool boundary, proving PE2-001/PE2-003's fixes survive there too, not just in `run_tracker` directly.
  - New deterministic CLI tests assert `anticharon check --zdr --json`'s printed JSON shape and `anticharon check --zdr`'s human-readable output actually render the `POLICY_UNROUTABLE` warning line, not just that the underlying warning object exists.
  - `tracker.py`'s `fetch_openrouter_models()`, `fetch_endpoint_policy_pricing()`, and `fetch_effective_pricing_history()` now validate the *nested* `data` payload's type (not just the request/parse outcome) — a wrong-typed nested `data` (e.g. a mapping instead of a list, or a list of non-dict entries) degrades to the documented empty value instead of crashing a downstream consumer with `AttributeError`.
  - `discovery.py`'s `fetch_catalog()` gets the identical nested-type guard for the same reason (browsing the full public catalog is more exposed to this than the shortlist tracker path).
  - `storage.py`'s `read_history()` now isolates a malformed CSV row instead of aborting the whole read — one bad row (e.g. a non-numeric price cell) no longer silently discards every model listed after it in `history.csv`.
  - `log_parser.py`'s `parse_activity_log()` clamps a row's cached-token count to that row's own prompt-token count, preventing a corrupted export (`tokens_cached > tokens_prompt`) from driving the whole log's `weight_uncached_prompt` negative. **Known gap, deferred (non-release-blocking):** this clamp does not yet floor a raw negative token count in any column — see `docs/BACKLOG.md`'s negative-token-count hardening entry.
  - Full evidence in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-006`.

### Fixed
- **PE2-007 — `anticharon test`'s Mathematical Engine check now verifies the actual production pricing formula (`src/anticharon/tester.py`):**
  - The diagnostic previously evaluated an arbitrary, hardcoded `(1.0 * 0.99) + (2.0 * 0.01)` two-component calculation with no connection to the production pricing function at all — it would still report `[PASS] Mathematical Engine: Verified` even if the real cache-aware three-component formula (ADR-2026-0002-TOKENS-CACHED) regressed or were removed entirely.
  - Now calls the actual production `calculate_effective_cost` (`src/anticharon/pricing.py`) with two of the ADR's independently-derived golden cases as reference values: a cache-heavy case (85% cached — fails if cached-token pricing is ignored/omitted) and a zero-cache case (confirms the uncached path stayed correct).
  - New `tests/test_tester.py` proves the fix is load-bearing: injects a broken (legacy 2-component-equivalent) `calculate_effective_cost` and confirms `run_self_test()` now genuinely reports failure — something the original hardcoded check could never have caught, by construction.
  - Full evidence in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-007`.
- **PE2-008 — `cache_hit_rate_used` now reports the real cache-hit rate, not a token weight (`src/anticharon/pricing.py`, `tracker.py`, `models.py`):**
  - `PricePoint.cache_hit_rate_used` was assigned `weight_cached_prompt` directly — cached prompt tokens as a share of *all* tokens (including completion), not the cache-hit rate (cached prompt tokens as a share of *prompt* tokens only). For the default config, this reported `0.764478` instead of the correct `0.766701`.
  - New `derive_cache_hit_rate(weight_uncached_prompt, weight_cached_prompt)` computes the real rate (`weight_cached_prompt / (weight_uncached_prompt + weight_cached_prompt)`); live-verified this round-trips exactly to the original interim default cache-hit-rate (`0.766701`) that `config.py`'s default weights were themselves derived from. Zero-prompt-weight (a degenerate 100%-completion mix) is explicitly defined as `0.0`, never a division error or a fabricated rate.
  - Full evidence in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-008`.

### Changed
- **PE2-009 — Planning and validation documents synchronized (`docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`, `PLAN.md`; `tests/test_analytics.py`, `test_storage.py`):**
  - Removed an accidentally duplicated empty `## 3. Acceptance Criteria` heading and a duplicated, superseded `### Verification` section in `EXECUTION_CONTRACT.md`.
  - Filled in the Sample Golden Case's `<explicit Anticharon-defined behavior>` placeholder for single-observation dispersion: `0.0%` (the coefficient of variation of a single data point is mathematically zero) — verified against the actual implementation and locked in by a new test, `tests/test_analytics.py::test_single_observation_zero_dispersion_golden_case`.
  - `PLAN.md`'s "Resolved divergences" item 9 claimed `read_history()` was "kept backward-compatible for existing local files" — directly contradicting the "Core pricing semantics" section above it and a later commit that explicitly dropped that shim. Corrected to match both (no shim; a stale old-format `history.csv` degrades gracefully to empty history) and now backed by a real regression test, `tests/test_storage.py::test_history_csv_old_pre_rename_format_degrades_gracefully` — closing a genuine gap in `EXECUTION_CONTRACT.md`'s own Storage acceptance criterion ("either backward-compatible or has an explicit, *tested* migration/fallback path"), which this fallback path had never actually had a test for until now.
  - Confirmed via search: no other unresolved placeholders or contradictory normative statements remain; all ten finding IDs (PE2-001 through PE2-010) remain present and stable in the ledger; no absolute host filesystem paths anywhere in the initiative's docs.
  - Full evidence in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-009`.

### Changed
- **PE2-010 — Lint/test tooling moved to a development dependency group; CI lint-gate policy documented (`pyproject.toml`, `uv.lock`, `AGENTS.md`, `docs/plans/pricing-engine-v2/EXECUTION_CONTRACT.md`):**
  - `pytest`/`ruff` were declared as runtime `dependencies`, so an end user installing Anticharon (`pip install`/`uv tool install`) pulled in both dev-only tools. Moved to a PEP 735 `[dependency-groups]` `dev` group instead — `uv sync` in this repo still installs it by default (no local-development impact), but the built wheel's `Requires-Dist` no longer lists either. Verified directly by building the wheel (`uv build --wheel`) and inspecting its `METADATA`: `Requires-Dist` is now only `mcp>=1.3.0` and `requests>=2.31.0`.
  - `ruff check src tests` currently reports 251 pre-existing findings unrelated to any single tracked initiative — this finding's own text says to "add a CI lint gate only when its scope is clean and explicitly documented." Since it isn't clean, no blanket `ruff` step was added to `.github/workflows/ci.yml` (still `uv run pytest` + `uv run anticharon test`, matching what `AGENTS.md`/`EXECUTION_CONTRACT.md` now explicitly document). The deferral itself — and the lint-scope rule for future initiative work ("changed files must be clean, pre-existing debt is out of scope") — is now written down in `AGENTS.md` (Rule 8) rather than left as unwritten practice.
  - Also discovered, disclosed, and explicitly deferred (not fixed, out of this finding's affected-files scope): `EXECUTION_CONTRACT.md`'s Verification section describes an emergency-bypass `smoke` pytest subset that does not actually exist anywhere in the repository. Recorded as its own item in `EXECUTION_CONTRACT.md`'s Deferred section for a future round.
  - Full evidence in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-010`.

## [0.5.2] - 2026-09-16

### Changed
- **`model discover` wording no longer implies AI-powered curation (`src/anticharon/cli.py`, `README.md`):**
  - The command's help/description text and README's feature description were written in a way that read like an AI-powered discovery/recommendation engine, when it's actually a plain multi-criteria filter (keyword substring, modality, price thresholds) over the live catalog, sorted cheapest-first. Reworded both to say "filters by criteria you provide" and explicitly disclaim "no AI ranking, curation, or recommendations." No behavior, flag, or command-name change — light-touch wording pass only. `discover_models` (the MCP tool name) and the `discover` subcommand name itself are unchanged, per explicit scope.

## [0.5.1] - 2026-09-16

### Fixed
- **`model discover --zdr` no longer live-checks the full catalog before filtering (`src/anticharon/discovery.py`, `cli.py`, `config.py`):**
  - `fetch_catalog()` no longer performs any live ZDR check itself (the `zdr_only` param is removed from it entirely) — the live per-endpoint check is now a separate, opt-in step (`apply_zdr_filter()`) applied *after* `filter_catalog()`, so it only ever runs against models actually matching the user's query/filters, not the full ~440-model catalog. Live-verified: an unfiltered `discover --zdr` used to live-check every candidate still in the catalog after the sentinel-price guard; it's now capped (see below) regardless of how broad the query is.
  - New config key `max_zdr_check_count` (default `10`, same pattern as `spike_threshold_pct`/`min_tracking_days_for_profile`): caps how many of the (already-filtered) candidates get a live ZDR check in one `discover --zdr` command, taking the cheapest N by blended price. **Never silently truncated** — when the filtered candidate list exceeds the cap, a clear warning is printed (and included as `zdr_warning` in `--json` output) naming exactly how many of how many were checked. `run`/`check --zdr` are unaffected — shortlists are inherently small (7–9 models typically), so this cap only matters for `discover`'s full-catalog case.

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
