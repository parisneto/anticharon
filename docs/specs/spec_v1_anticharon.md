# Technical Specification: Anticharon (v1)

**Document Version:** 1.1.0
**Status:** Approved
**Language:** English

---

## 1. Overview & Lore

### 1.1 The Mythos of Anti-Charon
In Greek mythology, **Charon** is the grim ferryman who demands an obol coin toll to ferry souls across the rivers Styx and Acheron. In the world of LLM agents (such as **Hermes Agent**), token consumption is the ever-accumulating toll of daily execution.

**Anticharon** is the counter-agent: the vigilant ferryman who continually monitors OpenRouter API pricing, detects rate spikes and discounts, computes weighted effective costs, and helps agents cross the token river for the lowest possible toll.

### 1.2 System Architecture Overview

```text
[ Cron / Schedule / CLI ] ───> [ Anticharon CLI ]
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
      [ OpenRouter API ]                           [ Local Storage ]
     (GET /api/v1/models)                           (./data/history.csv or ~/.anticharon/history.csv)
     * 10s timeout                                  * Compact 1-line-per-model CSV
     * Fallback to local cache                      * 30-day sliding price window
```

---

## 2. Token Weighting & Empirical Calibration Rationale

### 2.1 Why Local Calibration over Background API Polling? (Design Principles)
Automated background synchronization of billing metrics via management API keys might seem convenient, but Anticharon deliberately rejects account-level API polling in favor of local CSV calibration:
- **Least Privilege & Security:** Requesting broader management API scopes or keys with account-wide permissions just to check token ratios exposes unnecessary attack surfaces. Local file ingestion ensures user credentials stay completely isolated.
- **Zero Overhead & Total Control:** OpenRouter does not provide a single aggregated usage endpoint; doing it via live API requires heavy, rate-limited sequential calls. A lightweight local CSV export gives instant, absolute mathematical clarity without network dependencies.

### 2.2 Empirical Real-World Validation
Agentic coding workflows are overwhelmingly dominated by prompt tokens (context history, workspace file contents, system instructions, and tool outputs):
- **University of Washington TraceLab Evidence:** Empirical research from [*"TraceLab: Characterizing Coding Agent Workloads for LLM Serving"*](https://syfi.cs.washington.edu/blog/2026-06-25-tracelab/) ([live demo](https://tracelab.cs.washington.edu/), [GitHub](https://github.com/uw-syfi/TraceLab)) analyzing coding agent workloads (Sep 2025 – Jul 2026) recorded **114.2 billion input tokens** vs **391.8 million output tokens** (a **291.5 : 1 ratio**), yielding **99.66% input / 0.34% output**.
- **Author Operational Dataset (August 2026):** Ingestion of 159 agent generations (`openrouter_activity_2026-08-24.csv`) totaling **17,437,925 tokens** yielded **17,386,716 prompt tokens (99.71%)** vs **51,209 completion tokens (0.29%)**, differing by **only 0.05% (-0.0005)** from the 114B token academic baseline.
- **The Core Outcome:** Calculating blended prices with accurate input/output weighting eliminates cost anxiety, allowing developers and agents to run premium frontier models responsibly while dramatically reducing the "ferryman tax" and discouraging AI slop.

---

## 3. Mathematical Specifications & Formulas

### 3.1 The Three-Price Model: Advertised, Effective, Policy (`ADR-2026-0002-TOKENS-CACHED`)

Anticharon represents cost with three deliberately distinct numbers, never collapsed into one. The legacy single 2-component `Price_1M = (P_in × 0.9971) + (P_out × 0.0029)` formula is **removed** as an independent downstream path — every calculation below supersedes it.

- **`advertised_prompt_1m` / `advertised_completion_1m`** — the raw listed pair from the bulk `/api/v1/models` catalog headline. Never blended, never pinned to whichever endpoint is actually used. A transparency/comparison anchor only, never an input to any calculation.
- **`effective_price_1m`** — the cache-aware 3-component blend, computed against the *cheapest real endpoint* returned by the internal per-endpoint route (§ "Policy (ZDR) Pricing Data Source" below), not just the bulk catalog headline:
  ```text
  Effective_Cost = (Uncached_Tokens / 1e6 × P_uncached)
                 + (Cached_Tokens   / 1e6 × P_cache_read)
                 + (Completion_Tokens / 1e6 × P_completion)

  Effective_Price_1M = Effective_Cost / Total_Tokens × 1,000,000
  ```
  Equivalently, from calibrated weights alone (no token counts needed — `src/anticharon/pricing.py`'s `blended_rate_1m`):
  ```text
  Effective_Price_1M = (P_uncached × W_uncached) + (P_cache_read × W_cached) + (P_out × W_completion)
  ```
  Implemented as a pure function in `src/anticharon/pricing.py`, validated against 5 independently-derived golden cases in `tests/test_golden_pricing.py`, and wired into the live tracking path in `src/anticharon/tracker.py` (`resolve_policy_pricing`).
- **`policy_price_1m`** (optional) — the same blend, restricted to endpoints passing an active policy filter (Zero Data Retention to start, via `--zdr`). `None`/absent when no policy filter is active. `is_policy_routable` (`true`/`false`/`null`) reports whether at least one policy-compliant endpoint exists; `null` means "unknown" (the endpoint route failed), never a fabricated `false`.
- **`effective_price_1m` is never replaced by the policy price, in any surface (JSON `--json` output, `check_prices` MCP payload, or internal comparisons).** Every downstream comparison against historical data — `ma_3d`, `ma_7d`, `delta_7d_pct`, `PRICE_SPIKE`/`PRICE_DROP` — is computed against the unconstrained `effective_price_1m`, because `effective_prices.json` only ever stores unconstrained effective observations; comparing a policy-constrained *current* price against an unconstrained *historical* average would be an apples-to-oranges comparison. When a policy filter is active (`--zdr`), only shortlist **ranking** for display order and the `BEST_OPTION_CHANGED` recommendation switch to `policy_price_1m`; a model with no policy-compliant endpoint (`policy_price_1m` is `None`) is excluded from being ranked "cheapest" or recommended — see §3.7 rule 3 and `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001` (fixed: `src/anticharon/tracker.py`'s `_rank_price_1m`, `src/anticharon/models.py`'s `ModelPrice.to_dict()`).
- **Default (non-calibrated) weights:** `weight_uncached_prompt=0.232622`, `weight_cached_prompt=0.764478`, `weight_completion=0.0029` — the TraceLab-cited 99.71%/0.29% split decomposed by an interim pooled cache-hit-rate of `0.766701` (from the two real activity-log samples in `docs/sample/`; see `docs/plans/pricing-engine-v2/PLAN.md`, Deferred, for the backlog to replace this with a documented public source).
- **Cache-read price fallback:** when an endpoint omits `pricing.input_cache_read`, Anticharon defaults it to `10% of that endpoint's own uncached prompt price` (`resolve_cache_read_price_1m`), never `$0`.

### 3.1a Sentinel/Invalid Listed Price Guard

OpenRouter meta-router models (`openrouter/auto`, `auto-beta`, `fusion`, `pareto-code`, `bodybuilder` — live-verified 2026-09-16) list `pricing.prompt`/`pricing.completion` as the raw sentinel string `"-1"`, meaning "routes to whatever backing model at that model's own price," not a real fixed cost. §3.1's formulas convert raw pricing by multiplying by `1,000,000`; applied naively to a sentinel this produces `-1,000,000.0/1M`, which then sorts as the cheapest model everywhere pricing is compared. `src/anticharon/pricing.py`'s `is_valid_listed_price()` rejects any negative listed price (zero is still valid — that's how genuine free/promo-tier models are listed); `run_tracker` (`tracker.py`) and `fetch_catalog` (`discovery.py`) both skip a model failing this check rather than surfacing it.

### 3.2 Policy (ZDR) Pricing Data Source

Provider-routable pricing (`effective_price_1m`, `policy_price_1m`) comes from an internal, unauthenticated frontend route, not the public `/models/{slug}/endpoints` call originally assumed in an earlier revision of this initiative:

```text
GET /api/frontend/v1/stats/endpoint
    ?latencyMetric=latency&perfWorkload=text_generation
    &permaslug={canonical_slug}&variant=standard
```

**Correction (live-verified 2026-09-16):** the public `/models/{slug}/endpoints` call's `status` field does **not** carry ZDR-routability on an unauthenticated request — it reports `0` (routable) for every provider regardless of real policy. The real, unauthenticated ZDR signal is `provider_info.dataPolicy.retainsPrompts` (bool) per endpoint in the frontend route's `data[]` array: `false` = Zero Data Retention compliant, `true` = not. This route returns a strict superset of the pricing fields already relied on (`pricing.prompt`/`completion`/`input_cache_read`/`input_cache_write`/`discount`/`overrides`) plus this policy data the public route can never provide, so it supersedes `/models/{slug}/endpoints` entirely for this project. `canonical_slug` is resolved directly from the bulk catalog's own `canonical_slug` field per model (confirmed present; no separate resolution call needed).

Graceful degradation: on failure (network error, malformed response, or a model with no endpoint data), Anticharon treats the model as policy-unknown (`is_policy_routable: null`) and falls back to the bulk catalog's own headline pricing for `effective_price_1m` — never a fabricated ZDR warning, never a crash.

### 3.3 Moving Averages (`MA_3d` and `MA_7d`)

`MA_3d`/`MA_7d` are precalculated fresh each sync from the granular `effective_prices.json` store (§5.2), not accumulated by shifting a list — see §3.4. Both average only the **non-null** slots present in their window (`d1..d3` for `MA_3d`, `d1..d7` for `MA_7d`); a slot with no real observation contributes nothing and is never fabricated:

```text
MA_3d = mean(non-null values among [d1, d2, d3])
MA_7d = mean(non-null values among [d1, d2, d3, d4, d5, d6, d7])
```

If none of a window's slots have data (e.g. day 1 with no backfill at all), `MA_3d`/`MA_7d` fall back to today's `effective_price_1m` — the same cold-start intent as before, applied per-window instead of by padding fabricated history.

### 3.4 Historical Window Derivation (supersedes the old per-run "shift")

Historical prices are still surfaced as a 9-slot array `[d1, d2, d3, d4, d5, d6, d7, d15, d30]`, but each slot is now **derived fresh, every sync**, from `effective_prices.json`'s dated daily observations (`derive_history_window` in `storage.py`) rather than shifted by one position per run:

```text
d{N} = the observation dated exactly N calendar days before today, if one exists, else null (never fabricated)
```

**Same-day-rerun bug (fixed):** the previous mechanism did `New_Prices = [Today_Price] + Prev_Prices[:8]` unconditionally on every run, with no check against the calendar date — running `anticharon run` twice in one day silently corrupted the window (each run counted as a full day-shift). Deriving `d1..d30` fresh from dated observations makes this a structural non-issue: re-running any number of times on the same calendar day is idempotent, since there is no "shift" left to double-apply.

### 3.5 Cold-Start & Backfill Handling
When a model is first added to the tracking shortlist:
- `effective_prices.json` gets a new entry with `first_seen` = today and up to ~30 days of real backfilled observations from the internal effective-pricing route (§5.2) — not a fabricated flat history.
- Slots with no real observation (including a model with zero backfill available, e.g. a `~`-prefixed router alias with no fixed permaslug identity) stay `null`, never a duplicate of today's price.
- `MA_3d`/`MA_7d` fall back to today's `effective_price_1m` only when their entire window is null (§3.3) — this prevents `NaN`, division-by-zero, or false volatility spikes on day 1 without fabricating history.

### 3.7 Volatility & Anomaly Detection
Anticharon evaluates percentage variation against the 7-day moving average:

```text
Delta_7d_Pct = ((Effective_Price_1M - MA_7d) / MA_7d) × 100
```

(Under an active policy filter, `Policy_Price_1M` replaces `Effective_Price_1M` here — see §3.1.)

#### Warning Trigger Rules:
1. **`PRICE_SPIKE`**: Triggered when `Delta_7d_Pct ≥ +spike_threshold_pct` (default: `+20.0%`). Indicates a price hike.
2. **`PRICE_DROP`**: Triggered when `Delta_7d_Pct ≤ -spike_threshold_pct` (default: `-20.0%`). Indicates a discount or promotion.
3. **`BEST_OPTION_CHANGED`**: Triggered when the lowest-cost model in the shortlist is different from the configured `current_default` model (the first entry in `shortlist.json`). Under an active policy filter (`--zdr`), "lowest-cost" ranks by `policy_price_1m`; a model with no policy-compliant endpoint (`policy_price_1m` is `None`) is never eligible to be ranked "cheapest" or recommended as the suggested option, even if its unconstrained `effective_price_1m` is the lowest in the shortlist (`docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001`).
4. **`POLICY_UNROUTABLE`**: Triggered (only when a policy filter is active, e.g. `--zdr`) when no endpoint passes the filter for a model. Carries `policy`, `excluded_providers`, and `reason` fields; never blocks the run, only warns.

---

## 4. OpenRouter Activity Log Calibration (`anticharon calibrate`)

To update operational weights whenever a fresh CSV is exported from the OpenRouter dashboard:
- Navigation: OpenRouter → Sidebar Logs → Select Period (e.g. Past 1 Month) → 3 dots menu → Export CSV.
- Columns processed: `tokens_prompt`, `tokens_completion`, `tokens_cached`.

### Computation Formula:
`parse_activity_log` (`src/anticharon/log_parser.py`) reads `tokens_prompt`, `tokens_completion`, and `tokens_cached` and computes the cache-aware 3-way split that feeds §3.1's formulas directly (the legacy 2-way `Weight_Prompt`/`Weight_Completion` split is removed — `Weight_Uncached_Prompt` + `Weight_Cached_Prompt` together are what `Weight_Prompt` used to be):

```text
Total_Prompt_Tokens     = sum(tokens_prompt)
Total_Completion_Tokens = sum(tokens_completion)
Total_Cached_Tokens     = sum(tokens_cached)
Total_Uncached_Tokens   = Total_Prompt_Tokens - Total_Cached_Tokens
Total_Tokens             = Total_Prompt_Tokens + Total_Completion_Tokens

Weight_Uncached_Prompt = Total_Uncached_Tokens / Total_Tokens
Weight_Cached_Prompt   = Total_Cached_Tokens   / Total_Tokens
Weight_Completion      = Total_Completion_Tokens / Total_Tokens
Cache_Hit_Rate         = Total_Cached_Tokens   / Total_Prompt_Tokens
```

`anticharon calibrate` persists `weight_uncached_prompt`/`weight_cached_prompt`/`weight_completion` to `shortlist.json` (§6). Logs exported before `tokens_cached` existed (or missing the column) still parse correctly: the cached bucket defaults to 0, i.e. 100% uncached.

---

## 5. Data Storage: Two Files, Two Lifecycles

### 5.1 `history.csv` — compact, fast-read summary (one line per model)

**Breaking rename:** the blended-price column is `effective_price_1m`, not `current_price_1m` — pre-launch, single-digit testers, so there is deliberately no backward-compatibility shim; a stale local `history.csv` from before this change should be deleted/regenerated.

### Header Format:
```csv
model,last_updated,effective_price_1m,advertised_prompt_1m,advertised_completion_1m,ma_3d,ma_7d,d1,d2,d3,d4,d5,d6,d7,d15,d30
```

### Column Definitions:
| Column | Type | Description |
| :--- | :--- | :--- |
| `model` | string | OpenRouter model ID / slug (e.g. `openai/gpt-5.6-luna`) |
| `last_updated` | ISO-8601 string | UTC timestamp of last update |
| `effective_price_1m` | float | Cache-aware blended price per 1M tokens, cheapest real endpoint (§3.1) |
| `advertised_prompt_1m` | float | Raw listed bulk-catalog prompt price (never blended, §3.1) |
| `advertised_completion_1m` | float | Raw listed bulk-catalog completion price (never blended, §3.1) |
| `ma_3d` | float | 3-day moving average, derived fresh each sync (§3.3) |
| `ma_7d` | float | 7-day moving average, derived fresh each sync (§3.3) |
| `d1` to `d7` | float or empty | Prices from 1 to 7 days ago. **Nullable** — empty means no real observation for that day, never a fabricated value (§3.4/§3.5). |
| `d15` | float or empty | Price recorded 15 days ago. Nullable. |
| `d30` | float or empty | Price recorded 30 days ago. Nullable. |

### 5.2 `effective_prices.json` — granular per-model, per-provider daily observations

Same data directory as `history.csv`, same path-resolution hierarchy (§6.1). This file is the **source of truth** for history; `history.csv`'s `d1..d30`/MA columns are derived from it (§3.4), not the other way around. Its refresh cadence is independent of `history.csv`'s per-run cadence — a model is only re-fetched when its entry is stale (default: older than 24 hours), not on every `anticharon run`.

```json
{
  "openai/gpt-5.6-luna": {
    "canonical_slug": "openai/gpt-5.6-luna-20260709",
    "first_seen": "2026-08-16",
    "last_synced": "2026-09-16T12:00:00+00:00",
    "observations": [
      {"date": "2026-08-16", "effective_price_1m": 0.0757},
      {"date": "2026-08-17", "effective_price_1m": 0.0812}
    ]
  }
}
```

- `first_seen`: the calendar date this model was first tracked. Drives the analytics `NEWLY_TRACKED` threshold (§"Historical Analytical Intelligence & Pricing Profiles" below) — never overwritten once set.
- `observations`: one entry per calendar day, the cheapest endpoint's blended $/1M that day (input/output combined via the locally calibrated `weight_completion` split — the internal effective-pricing route's own per-endpoint series is already cache-weighted by that provider's real traffic that day, so only the input/output combination is Anticharon's to apply).
- 28-day backfill source: `GET /api/frontend/v1/stats/effective-pricing?permaslug={canonical_slug}&shape=v7&variant=standard&range=1m`. **The `range=1m` parameter is required** — live-verified 2026-09-16: the bare/default call (no `range`) only returns the last ~8 days, not ~30.
- Graceful degradation: a `~`-prefixed router alias (e.g. `~deepseek/deepseek-pro-latest`) returns an empty-but-200-OK payload (live-verified — "latest" has no fixed permaslug identity to have history against). A transient failure never overwrites previously accumulated real `observations` with empty data; `last_synced` still advances so a permanently-empty model isn't re-fetched every run.

---

## 6. Configuration Schema (`shortlist.json`)

```json
{
  "shortlist": [
    "openai/gpt-5.6-luna",
    "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-v4-flash-0423",
    "qwen/qwen3.7-flash",
    "google/gemini-3.1-flash-lite",
    "minimax/minimax-m2.7",
    "google/gemini-2.5-flash-lite"
  ],
  "weight_uncached_prompt": 0.232622,
  "weight_cached_prompt": 0.764478,
  "weight_completion": 0.0029,
  "spike_threshold_pct": 20.0,
  "min_tracking_days_for_profile": 14,
  "max_zdr_check_count": 10
}
```

`min_tracking_days_for_profile` (default `14`, half the 28-day backfill window): elapsed calendar days since a model was first tracked before analytics classification ("Historical Analytical Intelligence & Pricing Profiles" below) moves past `NEWLY_TRACKED`. Configurable per shortlist, same as `spike_threshold_pct`.

`max_zdr_check_count` (default `10`): caps how many candidate models `anticharon model discover --zdr` will live-check for ZDR routability in a single command (§7 CLI Command Interface). Applied only after local filters (`query`, `--filter`, `--promo`, price/modality bounds) narrow the candidate list — never before — and only to the cheapest N candidates by blended price. If the filtered list still exceeds the cap, Anticharon never silently checks a subset and presents it as complete: it prints an explicit warning naming how many of how many were checked (`zdr_warning` in `--json` output) and proceeds with the cheapest N. `run`/`check --zdr` are unaffected by this cap — shortlists are inherently small (7–9 models typically), so the cap only matters for `discover`'s full-catalog case.

### 6.1 Path Resolution Hierarchy:
1. **CLI Arguments:** `--config <path>` and `--data-dir <path>` (highest priority).
2. **Environment Variables:** `ANTICHARON_CONFIG` and `ANTICHARON_DATA_DIR`.
3. **Local Workspace Mode (Running inside repo):**
   - Config: `./config/shortlist.json` (or `./config/shortlist.example.json`)
   - Data: `./data/history.csv`
4. **Standalone / Tool Mode (When installed via `uv tool install` or run as an MCP server):**
   - Config: `~/.anticharon/shortlist.json`
   - Data: `~/.anticharon/history.csv`

---

## 6.2 Hermes Agent Integration & Model Auto-Sync

When deployed in environments alongside **Hermes Agent**, Anticharon automatically resolves and synchronizes the active running models directly from Hermes rather than relying exclusively on static defaults.

### Hermes Configuration Resolution Hierarchy:
1. Explicit CLI argument: `--hermes-config <path>`
2. Environment variable: `HERMES_CONFIG` (direct path to config file)
3. Environment directory: `$HERMES_HOME/config.yaml`
4. Standard user home path: `~/.hermes/config.yaml`
5. Interactive prompt (TTY only): If missing and interactive, prompt user for path.
6. Standalone fallback: If not found in non-interactive/cron mode, log a prominent warning banner and fall back cleanly to `shortlist.json`.

### Two-Tier Safe Extraction Architecture:
- **Tier 1 (Hermes CLI):** If `hermes` binary is present on `$PATH`, queries `hermes config get model` and `hermes config get fallback_providers` directly (< 1.5s timeout).
- **Tier 2 (Stream-Grep File Scanner):** If `hermes` CLI is not on `$PATH`, inspects the file using a line-by-line streaming regex scanner.
  - Matches `default: <model_slug>` (verified for OpenRouter provider).
  - Matches `fallback_providers: <json_array>` or multi-line YAML fallbacks.
  - Zero `pyyaml` dependency.
  - Constant memory footprint: reads line-by-line without buffering the file.
  - Zero secret leaks: API keys, system prompts, and tokens in other YAML sections are never read or stored.

### Model Placement & Synchronization Rules:
- The Hermes `default` model is always placed at index 0 (`shortlist[0]`), receiving the `★ [DEFAULT]` badge and serving as the baseline for `BEST_OPTION_CHANGED` alerts.
- OpenRouter fallback models follow in order.
- Newly discovered models are automatically initialized in `history.csv`/`effective_prices.json` using the cold-start & backfill rule (§3.5).
- User-configured weights (`weight_uncached_prompt`, `weight_cached_prompt`, `weight_completion`, `spike_threshold_pct`, `min_tracking_days_for_profile`) are preserved during synchronization.
- Upgrades/reinstallation resilience: If `~/.anticharon/` is deleted during an update, the next execution re-creates `~/.anticharon/shortlist.json` automatically.
- Opt-out: Pass `--no-hermes` to suppress Hermes auto-detection and run purely standalone.

---

## 3.6 Historical Analytical Intelligence & Pricing Profiles

Anticharon inspects the full 30-day temporal window stored in `history.csv` (`[d1..d7, d15, d30]`) and applies statistical dispersion analysis alongside live catalog sibling relationship tracking:

### Metric Definitions:
- **Mean Price:** `μ = sum(prices) / 10`
- **Standard Deviation:** `σ = sqrt(sum((p - μ)²) / 10)`
- **Coefficient of Variation:** `CV = (σ / μ) × 100%`
- **30-Day Net Shift:** `Delta_30d_Pct = ((Current_Price - Price_d30) / Price_d30) × 100%`

### Deterministic Model Profile Categories:
1. **`STABLE` (`🛡️ STABLE`):**
   - Condition: `CV < 2.5%` and `|Delta_30d_Pct| < 5%`.
   - Meaning: Mature, predictable pricing. Low budget risk for agents and scheduled cron pipelines.
2. **`PROMO_ENDED` (`📈 PROMO_ENDED`):**
   - Condition: Prior baseline (`d15` or `d30`) was `≥ 25%` cheaper than current price, and current price has remained elevated for `≥ 2` days.
   - Meaning: Promotional or introductory discount has expired. The higher price is the new baseline.
3. **`SUNSETTING` (`⚠️ SUNSETTING`):**
   - Condition: Current price `≥ Price_d30`, AND the OpenRouter catalog or shortlist contains a newer version in the same model family (e.g. Gemini 3.8 vs 3.7) that is equal or cheaper in price.
   - Meaning: Vendor is forcing architectural migration away from the legacy slug.
4. **`VOLATILE` (`⚡ VOLATILE`):**
   - Condition: `CV ≥ 12%`, or frequent reversals in directional delta across the window.
   - Meaning: Unpredictable rate fluctuations. Monthly cost estimation is unreliable.
5. **`DISCOUNTED` (`🏷️ DISCOUNTED`):**
   - Condition: Current price is `≥ 20%` lower than 30-day baseline (`Current_Price ≤ 0.80 × Price_d30`).
   - Meaning: Active promotion or permanent rate reduction. High-value window for large context or batch tasks.
6. **`CREEPING_INFLATION` (`🐌 CREEPING`):**
   - Condition: Steady upward drift (`Price_d30 < Price_d15 < Price_d7 < Current_Price`) with total rise between `+5%` and `+25%` without triggering single-day spike alerts.
   - Meaning: Stealth inflation by provider.
7. **`NEWLY_TRACKED` (`🌱 NEWLY_TRACKED`):**
   - Condition: fewer than `min_tracking_days_for_profile` (default `14`) calendar days have elapsed since the model was first tracked (`effective_prices.json`'s `first_seen`) — **not** a count of populated history slots, since backfill can leave gaps (e.g. `d1` and `d15` populated but nothing between) or a model's elapsed-time-tracked state can outpace how many slots happen to be filled. Elapsed time unknown (no store entry yet) is treated the same as "not enough" — the safe default.
   - Meaning: Insufficient tracking history yet, regardless of what the available slots show. Once `min_tracking_days_for_profile` is satisfied, a model can be classified `STABLE`/`VOLATILE`/etc. even with real gaps in its history.

---

## 7. CLI Command Interface

### Primary Commands & Options:
```bash
# 1. Standard execution: Fetch API, update ./data/history.csv, print report & alerts
anticharon run

# 2. Dry run / Check: Fetch API, calculate prices without modifying history.csv
anticharon check --dry-run

# 3. Analytical Intelligence: Evaluate 30-day historical profiles and trajectory table
anticharon check --profile
anticharon run --profile
anticharon check --profile --json

# 4. History Subcommand: Audit 30-day temporal metrics and export raw CSV
anticharon history
anticharon history --profile
anticharon history --csv
anticharon history --json

# 5. Agent-to-Agent Info: Output llms.txt briefing directly to stdout
anticharon info
anticharon info --json

# 6. Suppress Hermes auto-detection and run purely standalone
anticharon run --no-hermes
anticharon check --no-hermes

# 7. Explicit Hermes config path
anticharon run --hermes-config /custom/path/to/config.yaml

# 8. Output structured JSON (ideal for Hermes or script piping)
anticharon run --json

# 9. Custom paths and timeouts
anticharon run --config ./my_config.json --data-dir ./my_data --timeout 15.0

# 10. Pre-flight self-test: Validate runtime, config, math, permissions, network, and Hermes integration
anticharon test [--json]

# 11. Calibrate weights from OpenRouter activity log and update shortlist.json
anticharon calibrate path/to/openrouter_activity.csv [--dry-run]

# 12. Explicitly sync models from Hermes config
anticharon model sync [--hermes-config PATH] [--dry-run]

# 13. Model Management (Add / Remove / List)
anticharon model add "google/gemini-3.7-flash" [--dry-run]
anticharon model remove "minimax/minimax-m2.7" [--dry-run]
anticharon model list [--json]

# 14. Model Discovery & Exploration
anticharon model discover "gemini"
anticharon model discover --promo
anticharon model discover "qwen" --modality text --max-price 0.50
anticharon model discover --filter "openai" --filter "price < 10"
anticharon model discover --zdr  # live-checks only the (already-filtered) cheapest max_zdr_check_count candidates
anticharon model discover "gemini" --zdr  # narrow filters first to check more of your actual matches

# 15. Policy (ZDR) Pricing: restrict effective/policy price to ZDR-compliant endpoints
anticharon check --zdr --json
anticharon run --zdr

# 16. Ergonomic Help Subcommand: Display top-level or subcommand usage
anticharon help
anticharon help run
anticharon help model
anticharon help model discover
```

---

## 8. Safety, Resilience & Network Fallback

1. **Timeout Control:** Every OpenRouter HTTP request has an explicit `10.0` second timeout.
2. **Self-Describing Fallback Schema:** If the OpenRouter API fails (HTTP error, connection reset, timeout), Anticharon reads `history.csv`, logs a non-fatal warning, and returns the last known prices. To prevent LLM agents from confusing HTTP cache fallbacks with model failover providers, the JSON schema includes explicit fields:
   - `data_source`: `"live_api"` (successful HTTP request) or `"cached_history"` (network failure fallback).
   - `api_offline_fallback`: `true` if OpenRouter API failed and local cache was used; `false` otherwise.
   - `fallback`: Legacy boolean alias for `api_offline_fallback` maintained for backward compatibility.
   - `_hints`: In-band field definitions dictionary included when `--hints` is passed.
3. **No Unhandled Crashes:** Agents relying on Anticharon via cron or automated pipelines receive valid structured data even during network disruptions.

---

## 9. Agent-to-Agent (A2A) Discovery Standard (`llms.txt`)

In compliance with the [`llms.txt`](https://llmstxt.org/) specification:
- Anticharon maintains a structured `llms.txt` document at the repository root and installs a copy to `~/.anticharon/llms.txt`.
- Any autonomous LLM agent, MCP host, or CLI script can run `anticharon info` to stream the machine-readable operational briefing directly into its context window.
- The document provides concise operational instructions, CLI parameter syntax, JSON schemas, and Hermes configuration commands without unnecessary human prose.

---

## 10. Model Context Protocol (MCP) Server Architecture

Anticharon natively exposes a standard Model Context Protocol (MCP) server over `stdio` via `anticharon mcp`. This enables autonomous LLM agents (such as Hermes Agent, Claude Desktop, and Cursor) to monitor OpenRouter pricing, query historical intelligence, and discover catalog alternatives on demand.

### 10.1 Protocol & Transport Specifications
- **Transport:** Standard input/output (`stdio`) using JSON-RPC 2.0.
- **Stdio Isolation Rule:** `stdout` is reserved strictly for valid JSON-RPC frames. All logging, status banners, non-fatal cache fallback notices, and error logs are directed to `stderr`.
- **SDK Implementation:** Python standard `mcp>=1.3.0` (`FastMCP`).

### 10.2 Exposed MCP Tools

#### 1. `check_prices`
- **Description:** Fetches current OpenRouter model pricing for the monitored shortlist, calculates the cache-aware advertised/effective/policy price triple (§3.1), computes 7-day moving averages, evaluates volatility alerts (PRICE_SPIKE, PRICE_DROP, BEST_OPTION_CHANGED, POLICY_UNROUTABLE), and attaches 30-day analytical intelligence profiles.
- **Parameters:**
  - `force_refresh` (boolean, optional, default: `false`): Force fresh HTTP fetch from OpenRouter API, ignoring local cache.
  - `dry_run` (boolean, optional, default: `true`): Calculate prices without updating `history.csv`/`effective_prices.json`.
  - `include_analytics` (boolean, optional, default: `true`): Attach 30-day statistical profiles, badges, and sibling alternatives.
  - `zdr_only` (boolean, optional, default: `false`): Restrict `policy_price_1m` to Zero Data Retention-compliant endpoints (§3.2) and surface `POLICY_UNROUTABLE` warnings.
- **Return Payload:** Self-describing JSON dictionary containing `timestamp`, `data_source` (`live_api` or `cached_history`), `api_offline_fallback` (boolean), `prices_shortlist` (each entry carrying `effective_price_1m`, `advertised_prompt_1m`/`advertised_completion_1m`, and `policy_price_1m`/`is_policy_routable` when a policy filter is active), `priceWarnings`, `hermes_integration`, and in-band `_hints`.

#### 2. `get_model_history`
- **Description:** Audits 30-day temporal price history, volatility coefficient of variation (CV%), directional trends, and deterministic intelligence profiles (STABLE, PROMO_ENDED, SUNSETTING, VOLATILE, DISCOUNTED, CREEPING_INFLATION, NEWLY_TRACKED).
- **Parameters:**
  - `model_id` (string, optional): Specific model slug to inspect. If omitted, returns all shortlisted models.
  - `format` (string, optional, default: `"json"`): Output format (`"json"` for structured analytics or `"csv"` for raw historical table).

#### 3. `discover_models`
- **Description:** Queries and filters OpenRouter's live catalog (~417+ models) using multi-criteria keyword matching, promotional status, output modality, and price ceiling expressions, calculating real-world blended prices calibrated to user token weights.
- **Parameters:**
  - `query` (string, optional): Search query (e.g. `"gemini"`, `"qwen"`).
  - `promo_only` (boolean, optional, default: `false`): Filter for promotional or free models (:free, $0.00).
  - `modality` (string, optional, default: `"text"`): Modality filter (e.g. `"text"`).
  - `max_price` (number, optional): Maximum blended price per 1M tokens ($).
  - `limit` (integer, optional, default: `15`): Maximum number of matching models to return.

#### 4. `import_hermes_models`
- **Description:** Imports active default and fallback models from Hermes Agent configuration (`~/.hermes/config.yaml` or `$HERMES_HOME`) into Anticharon's shortlist. **Strictly read-only on Hermes**: never modifies Hermes configuration.
- **Parameters:**
  - `hermes_config_path` (string, optional): Explicit custom path to Hermes `config.yaml`.
  - `dry_run` (boolean, optional, default: `true`): Safe-by-default preview mode. When `true`, detects and returns Hermes models without modifying disk; set `dry_run=false` to persist into Anticharon's `shortlist.json`.
- **Response Safety Fields:**
  - `direction` (`"hermes→anticharon"`): Confirms one-way data flow.
  - `hermes_untouched` (`true`): Confirms Hermes configuration was not mutated.
  - `notice`: Explicit notification on preview vs persistence status.

### 10.3 Exposed MCP Resources
- `anticharon://llms.txt`: Machine-readable Agent-to-Agent operational briefing and schema definitions.
- `anticharon://history.csv`: Raw 30-day sliding history table (`model,last_updated,effective_price_1m,advertised_prompt_1m,advertised_completion_1m,ma_3d,ma_7d,d1..d7,d15,d30`).
- `anticharon://shortlist.json`: Active model shortlist and token weight configuration.

### 10.4 Exposed MCP Prompts
- `cost_spike_triage`: Prompt template guiding an agent to analyze a detected `PRICE_SPIKE` or `PROMO_ENDED` alert and formulate model switching recommendations.
- `model_migration_advisor`: Prompt template guiding migration from a `SUNSETTING` model to an equal or cheaper sibling alternative.
- `family_upgrade_discover`: Discovers newer generation models in the same provider family (e.g. Gemini, DeepSeek, Qwen) and evaluates cost-benefit migration.
- `daily_cost_briefing`: Generates an executive daily cost briefing of model prices, moving averages, and volatility alerts across the active shortlist.
- `budget_optimization_audit`: Audits the active shortlist to identify cost outliers, SUNSETTING legacy versions, and opportunities to reorder fallback providers.

### 10.5 Host Configuration Integration

#### Hermes Agent (`~/.hermes/config.yaml`):
```yaml
mcp_servers:
  anticharon:
    command: "uvx"
    args: ["--from", "git+https://github.com/parisneto/anticharon.git", "anticharon", "mcp"]
```
*(Or locally installed: `command: "anticharon"`, `args: ["mcp"]`)*

#### Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "anticharon": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/parisneto/anticharon.git", "anticharon", "mcp"]
    }
  }
}
```

### 10.6 Real-World Empirical Case Study: Gemini 3.7 vs 3.8 Migration

During live MCP Inspector validation on September 3, 2026, Anticharon evaluated live OpenRouter pricing against the 30-day temporal sliding window for Google Gemini models:
- **`google/gemini-3.7-flash`:**
  - Price rose from $0.37941 to $0.75881 (+100.0%).
  - Statistical Profile: `📈 PROMO_ENDED` with secondary badge `⚠️ SUNSETTING`.
  - Trajectory Sparkline: `$0.38 ──↑ $0.76 (+100.0%, CV: 26.96%)`.
  - Analytical Recommendation: `"Introductory promo ended (+100.0%). Sibling google/gemini-3.8-flash active at same/lower price ($0.759). Migrate to google/gemini-3.8-flash."`
  - Sibling Alternative: Automatically identified `google/gemini-3.8-flash` ($0.75881/1M) as the newer drop-in version.
- **`google/gemini-2.5-flash-lite` & `google/gemini-3.1-flash-lite`:**
  - Classified as `🛡️ STABLE` (CV: 0.01%, 30-day change: +0.01%).
- **`google/gemini-3.8-flash`:**
  - Classified as `🌱 NEWLY_TRACKED` ($0.75881/1M).
- **Core Outcome:**
  Rather than an agent blindly continuing to run an expired promo model at double the price, Anticharon's MCP server provided structured mathematical proof and actionable instructions (`hermes config set model.default "google/gemini-3.8-flash"`) in a single JSON tool call.

![Anticharon MCP Inspector Price Analytics](docs/images/MCP%20Inspector_price_change.png)




