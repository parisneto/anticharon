# Technical Specification: Anticharon (v1)

**Document Version:** 1.1.0
**Status:** Approved — v0.6.0 Beta
**Language:** English

Anticharon is in Beta. Its public interfaces may change without deprecation
until real-user and third-party feedback establish stable expectations.

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
- **`effective_price_1m` is never replaced by the policy price, in any surface (JSON `--json` output, `check_prices` MCP payload, or internal comparisons).** Every downstream comparison against historical data — `ma_3d`, `ma_7d`, `delta_7d_pct`, `PRICE_SPIKE`/`PRICE_DROP` — is computed against the unconstrained `effective_price_1m`, because `effective_prices.json` only ever stores unconstrained effective observations; comparing a policy-constrained *current* price against an unconstrained *historical* average would be an apples-to-oranges comparison. When a policy filter is active (`--zdr`), only shortlist **ranking** for display order and the `BEST_OPTION_CHANGED` recommendation switch to `policy_price_1m`. `policy_price_1m` being `None` is not by itself exclusionary — it covers two distinct states that are ranked differently (§3.2): a model **confirmed** unroutable (`is_policy_routable` is `false`) is excluded from being ranked "cheapest" or recommended, while a policy-**unknown** model (`is_policy_routable` is `null`, routability could not be determined) is *not* excluded — it ranks by its unconstrained `effective_price_1m` and can still be recommended, per §3.2's routable-by-default rule. See §3.7 rule 3, `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001`, and `#PE2-003` (fixed: `src/anticharon/tracker.py`'s `_rank_price_1m`, `src/anticharon/models.py`'s `ModelPrice.to_dict()`).
- **Default (non-calibrated) weights:** `weight_uncached_prompt=0.232622`, `weight_cached_prompt=0.764478`, `weight_completion=0.0029` — the TraceLab-cited 99.71%/0.29% split decomposed by an interim pooled cache-hit-rate of `0.766701` (from the two real activity-log samples in `docs/sample/`; see `docs/plans/pricing-engine-v2/PLAN.md`, Deferred, for the backlog to replace this with a documented public source).
- **Cache-read price fallback:** when an endpoint omits `pricing.input_cache_read`, Anticharon defaults it to `10% of that endpoint's own uncached prompt price` (`resolve_cache_read_price_1m`), never `$0`.

### 3.1a Sentinel/Invalid Listed Price Guard

OpenRouter meta-router models (`openrouter/auto`, `auto-beta`, `fusion`, `pareto-code`, `bodybuilder` — live-verified 2026-09-16) list `pricing.prompt`/`pricing.completion` as the raw sentinel string `"-1"`, meaning "routes to whatever backing model at that model's own price," not a real fixed cost. §3.1's formulas convert raw pricing by multiplying by `1,000,000`; applied naively to a sentinel this produces `-1,000,000.0/1M`, which then sorts as the cheapest model everywhere pricing is compared. `src/anticharon/pricing.py`'s `is_valid_listed_price()` rejects any negative listed price (zero is still valid — that's how genuine free/promo-tier models are listed) **and any non-finite price** (`Infinity`/`-Infinity`/`NaN`, corrected — GH-3): `float()` parses the raw strings `"Infinity"`/`"-Infinity"`/`"NaN"` without error, so `parse_required_price_1m()` can return a non-finite value for a malformed upstream catalog/endpoint entry; this is the single boundary every tracker/discovery call site already gates model/endpoint acceptance on, so rejecting non-finite values here keeps them out of every downstream consumer (pricing math, sorting, and chart rendering) without needing a non-finite check at each call site. `run_tracker` (`tracker.py`) and `fetch_catalog` (`discovery.py`) both skip a model failing this check rather than surfacing it.

**Nested-shape schema drift:** `fetch_catalog()` also validates that the bulk catalog's top-level `data` value is actually a list, and skips any list entry that isn't a dict, before iterating it — a wrong-typed nested `data` payload (e.g. a mapping, or a list containing non-dict entries) degrades to an empty catalog `[]` instead of raising `AttributeError`/`TypeError` out of the per-model parsing loop.

**Required-field guard (PE2-002, corrected 2026-09-17):** `pricing.prompt`/`pricing.completion` are *required* fields on both the bulk catalog and each per-endpoint entry — never optional with a `0` default. Live-verified 2026-09-17: every real catalog model and every real per-endpoint entry, including genuine free (`:free`) models, always includes both keys explicitly (free models list them as the string `"0"`, never by omitting the key). A prior implementation used `pricing.get("prompt", 0)`, so a missing key, `null` value, blank string, or non-numeric value silently defaulted to `0.0` — a fabricated free price, indistinguishable from a genuine `$0` model, that could then win "cheapest" sorting and `BEST_OPTION_CHANGED` recommendations. `src/anticharon/pricing.py`'s `parse_required_price_1m()` now returns `None` (not `0.0`) for a missing/blank/malformed required field; every call site (`tracker.py`'s advertised-price parsing and per-endpoint blending, `discovery.py`'s catalog parsing) skips a model/endpoint entirely when either required field is `None`, rather than pricing it at a fabricated `$0`. This is distinct from `pricing.input_cache_read`, which is genuinely optional and legitimately defaults per the 10%-of-uncached-prompt fallback above — only `prompt`/`completion` are required.

### 3.2 Policy (ZDR) Pricing Data Source

Provider-routable pricing (`effective_price_1m`, `policy_price_1m`) comes from an internal, unauthenticated frontend route, not the public `/models/{slug}/endpoints` call originally assumed in an earlier revision of this initiative:

```text
GET /api/frontend/v1/stats/endpoint
    ?latencyMetric=latency&perfWorkload=text_generation
    &permaslug={canonical_slug}&variant=standard
```

**Correction (live-verified 2026-09-16):** the public `/models/{slug}/endpoints` call's `status` field does **not** carry ZDR-routability on an unauthenticated request — it reports `0` (routable) for every provider regardless of real policy. The real, unauthenticated ZDR signal is `provider_info.dataPolicy.retainsPrompts` (bool) per endpoint in the frontend route's `data[]` array: `false` = Zero Data Retention compliant, `true` = not. This route returns a strict superset of the pricing fields already relied on (`pricing.prompt`/`completion`/`input_cache_read`/`input_cache_write`/`discount`/`overrides`) plus this policy data the public route can never provide, so it supersedes `/models/{slug}/endpoints` entirely for this project. `canonical_slug` is resolved directly from the bulk catalog's own `canonical_slug` field per model (confirmed present; no separate resolution call needed).

Graceful degradation: on failure (network error, malformed response, or a model with no endpoint data), Anticharon treats the model as policy-unknown (`is_policy_routable: null`) and falls back to the bulk catalog's own headline pricing for `effective_price_1m` — never a fabricated ZDR warning, never a crash.

**Policy-unknown is routable-by-default, and distinct from confirmed noncompliance (PE2-003, corrected 2026-09-17):** `fetch_endpoint_policy_pricing()` returns `[]` uniformly for every failure mode (timeout, connection error, HTTP error, malformed JSON, wrong response shape) *and* for a genuinely successful response reporting zero endpoints — there is no real endpoint pricing to judge routability from in any of these cases, so they are deliberately normalized into one signal. Every consumer of that signal must treat it as **policy-unknown**, never as confirmed noncompliance:
- `resolve_policy_pricing()` (`tracker.py`) leaves `is_policy_routable`/`policy_price_1m` at `None` whenever no endpoint actually yielded a usable price (gated on the resolved rates, not on whether the raw endpoint list happened to be non-empty) — this is what separates "checked, and none are ZDR-compliant" (confirmed, `is_policy_routable: false`) from "could not check at all" (unknown, `is_policy_routable: null`).
- **Ranking** (shortlist sort order and `BEST_OPTION_CHANGED` eligibility, `--zdr`/`run`/`check`): a policy-unknown model ranks by its unconstrained `effective_price_1m` — the same as if no policy filter were active for that one model — and *can* be recommended as the best option. A confirmed-unroutable model (`is_policy_routable: false`) ranks last and is *never* recommended. These must never share an outcome; conflating them was flagged during independent review of the PE2-001 remediation and fixed here.
- A new `PriceWarning` type, `POLICY_UNKNOWN`, surfaces this uncertainty explicitly whenever `zdr_only` is active and routability could not be determined for a model — distinct from `POLICY_UNROUTABLE` (§3.7), which is reserved for confirmed noncompliance only.
- `apply_zdr_filter()` (`discovery.py`, used by `model discover --zdr`) applies the same rule: a candidate with no endpoint data at all is **kept** in the filtered results (routable-by-default), not dropped as if confirmed noncompliant; the returned warning names which candidates were kept this way.

**The ASCII price spectrum chart is independent of ranking order:** `render_ascii_price_bar()` (`src/anticharon/chart.py`) renders a spectrum of the unconstrained effective `price_1m` only. It never assumes its input is already sorted by that key — under `--zdr` the caller legitimately hands it the policy-ranked list, in which a confirmed-unroutable model sorts last (rank `∞`) even when its effective price is the cheapest. The chart therefore sorts a local working copy by `price_1m` and derives its 100%-width scale from `max(price_1m)`, never from the last element. Consequences: bar widths are always monotonically non-decreasing (the triangle shape), no bar can exceed `max_bar_width`, and `🏆 [BEST]` always badges the lowest *effective*-price model. The tracker's own ZDR ranking for the main list and `BEST_OPTION_CHANGED` (above) is unaffected.

**Defensive non-finite safety (corrected, GH-3):** a non-finite `price_1m` (`inf`/`-inf`/`nan`) should already be rejected upstream by `is_valid_listed_price()` above, but the chart stays defensively safe regardless of what reaches it. An earlier revision derived scale from `max(p.price_1m for p in ordered)` unconditionally and computed each bar as `int(round(ratio * max_bar_width))`: if the maximum happened to be `+inf`, that same entry's own ratio became `inf / inf` (`NaN`), and `int(round(nan))` raised `ValueError`, crashing the entire chart render on one bad entry. `render_ascii_price_bar()` now derives both the scale (`max(...)`) and the 🏆 [BEST] badge (`min(...)`) from the *finite* subset of prices only; a non-finite entry still renders its own row — capped at `max_bar_width` rather than crashing — but is excluded from both the scale computation and the BEST determination (a `-inf` sentinel sorting first is never treated as the true cheapest price).

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

**Correction (PE2-001, 2026-09-16):** `Delta_7d_Pct` always uses the unconstrained `Effective_Price_1M`, even under an active policy filter — an earlier draft of this line claimed `Policy_Price_1M` replaced it, which is exactly the collapse-under-`--zdr` defect PE2-001 fixed. `MA_7d`/`MA_3d` are always derived from unconstrained effective historical observations (`effective_prices.json` never stores policy-price history), so comparing them against anything other than the unconstrained current effective price would be an apples-to-oranges comparison — see §3.1.

#### Warning Trigger Rules:
1. **`PRICE_SPIKE`**: Triggered when `Delta_7d_Pct ≥ +spike_threshold_pct` (default: `+20.0%`). Indicates a price hike.
2. **`PRICE_DROP`**: Triggered when `Delta_7d_Pct ≤ -spike_threshold_pct` (default: `-20.0%`). Indicates a discount or promotion.
3. **`BEST_OPTION_CHANGED`**: Triggered when the lowest-cost model in the shortlist is different from the configured `current_default` model (the first entry in `shortlist.json`). Under an active policy filter (`--zdr`), "lowest-cost" ranks by `policy_price_1m` when a model is confirmed policy-routable, `Effective_Price_1M` when a model's policy status is unknown (routable-by-default, PE2-003), and never by a confirmed-unroutable model (`is_policy_routable` is `false`), regardless of how cheap its unconstrained `effective_price_1m` is (`docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-001`, `#PE2-003`).
4. **`POLICY_UNROUTABLE`**: Triggered (only when a policy filter is active, e.g. `--zdr`) when real endpoint data was checked and none passed the filter for a model (confirmed noncompliance). Carries `policy`, `excluded_providers`, and `reason` fields; never blocks the run, only warns.
5. **`POLICY_UNKNOWN`**: Triggered (only when a policy filter is active) when routability could not be determined at all — the internal endpoint route failed, returned no usable pricing, or reported zero endpoints (§3.2's graceful-degradation rule). Distinct from `POLICY_UNROUTABLE`: this model is still treated as routable-by-default for ranking purposes. Carries `policy` and `reason` fields; never blocks the run, only warns.

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

The three finite numeric weights must each be in `[0, 1]` and sum to `1.0` within `0.000001`. A total inside that tolerance is normalized by its sum and rounded to six decimal places before persistence. Totals outside that tolerance and booleans, strings, NaN, infinity, or out-of-range values are rejected.

**Per-row clamp:** since `tokens_cached` is logically a subset of `tokens_prompt`, a row reporting more cached tokens than prompt tokens (corrupt/garbled export data) has its cached count clamped to that row's own `tokens_prompt` value before aggregation, so one bad row cannot drive the whole log's `Total_Uncached_Tokens` negative. **Known gap (deferred, tracked in `docs/BACKLOG.md`):** this clamp does not yet reject or floor a raw *negative* token count in any of the three columns — a row with, e.g., `tokens_cached=-50` still contributes a negative value to that column's total. Deferral status recorded in `docs/plans/pricing-engine-v2/RELEASE_VALIDATION.md#PE2-006`; a future pass should floor each parsed field at zero.

---

## 5. Data Storage: Three Files, Three Lifecycles (D-22)

### 5.1 `history.csv` — compact, fast-read summary (one line per model)

**Breaking rename:** the blended-price column is `effective_price_1m`, not `current_price_1m` — pre-launch, single-digit testers, so there is deliberately no backward-compatibility shim; a stale local `history.csv` from before this change should be deleted/regenerated.

**Malformed-row isolation:** `read_history()` parses each row independently — a single row with a non-numeric cell (e.g. from a truncated or corrupted write) is skipped individually rather than aborting the read for the rest of the file. Every model listed before and after a malformed row is still recovered.

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

### 5.2 `effective_prices.json` — granular per-model daily observations

**Correction (PE2-004, 2026-09-17):** this section's own heading previously read "per-model, per-provider daily observations," but the schema it describes below has never stored provider identity — it is one collapsed cheapest-price-per-day observation per model. The heading was simply wrong; see `docs/plans/pricing-engine-v2/PLAN.md`'s "Scope correction" note (under "Storage architecture") for the full reconciliation: `EXECUTION_CONTRACT.md`'s actual acceptance criteria never required provider-level persisted granularity, no downstream consumer in this codebase needs it, and building it speculatively would violate the Contract's own "concrete over general" Non-Goal. Provider-granular historical persistence is recorded as a deferred backlog candidate in `EXECUTION_CONTRACT.md`, to be scoped against a real future consumer if one is ever proposed.

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

### 5.3 `alerts.json` — latest persisted alerts (D-22)

Same data directory as `history.csv`/`effective_prices.json`, same path-resolution hierarchy (§6.1). Written **only** by `run`/`run_prices` (the only fetch-and-write path, §10.2); `check`/`check_prices` and `history`/`get_model_history` read it verbatim and never recompute it (D-19).

```json
{
  "timestamp": "2026-09-25T10:00:00+00:00",
  "default_model": "openai/gpt-5.6-luna",
  "data_source": "live_api",
  "price_warnings": [
    {"type": "PRICE_SPIKE", "model": "openai/gpt-5.6-luna", "message": "..."}
  ]
}
```

- Alert computation is decoupled from the fetch/update code path, so a local read never triggers network access or recalculation.
- `run --model X` / `run_prices(model_id=X)` replaces only `X`'s per-model alerts (`PRICE_SPIKE`/`PRICE_DROP`) and recomputes the cross-model `BEST_OPTION_CHANGED` alert from the currently stored price of every shortlisted model; every other model's persisted alert is kept unchanged (mixed recency, D-18 Rule 1).
- A full (unfiltered) `run` replaces the whole `price_warnings` list.
- **Policy (ZDR) results are never persisted** (D-28): `POLICY_UNROUTABLE`/`POLICY_UNKNOWN` and any ZDR-ranked `BEST_OPTION_CHANGED` exist only in that call's live response, never in `alerts.json`. The persisted `BEST_OPTION_CHANGED` is always derived from the unconstrained `effective_price_1m`.
- `NEXT_FALLBACK_PRICE` compares the explicit Hermes default with its immediate
  Hermes fallback (`order: 1`) using unconstrained effective prices. It carries
  `current_default` and `next_fallback`, and is persisted alongside
  `BEST_OPTION_CHANGED`; it does not treat a cheaper later fallback as the next
  failover. If either price is unavailable, `NEXT_FALLBACK_UNAVAILABLE` is
  persisted instead. Neither alert is produced without an explicit default.

---

## 6. Configuration Schema (`shortlist.json`)

```json
{
  "shortlist": [
    {"model": "openai/gpt-5.6-luna", "source": "hermes", "order": 0},
    {"model": "deepseek/deepseek-v4-flash-0731", "source": "hermes", "order": 1},
    {"model": "deepseek/deepseek-v4-flash-0423", "source": "manual"}
  ],
  "weight_uncached_prompt": 0.232622,
  "weight_cached_prompt": 0.764478,
  "weight_completion": 0.0029,
  "spike_threshold_pct": 20.0,
  "min_tracking_days_for_profile": 14,
  "max_zdr_check_count": 10
}
```

Shortlist entries identify their owner with `source` (`hermes`, `manual`, or
`import:<name>`). `order` records Hermes fallback position; position 0 is the
Hermes default. A manual default also uses `order: 0`. Legacy flat string lists
are interpreted as Hermes entries when Hermes is detected and manual entries
otherwise, then migrated to objects on the next config write. Hermes sync
replaces Hermes entries while preserving manual and other imported entries.
The default is selected only from an explicit `order: 0` entry; list position
never implies a default. When absent, Anticharon emits `NO_DEFAULT` and skips
default-based alerts.

`min_tracking_days_for_profile` (default `14`, half the 28-day backfill window): elapsed calendar days since a model was first tracked before analytics classification ("Historical Analytical Intelligence & Pricing Profiles" below) moves past `NEWLY_TRACKED`. Configurable per shortlist, same as `spike_threshold_pct`.

`max_zdr_check_count` (default `10`): caps how many candidate models `anticharon model discover --zdr` will live-check for ZDR routability in a single command (§7 CLI Command Interface). Applied only after local filters (`query`, `--filter`, `--promo`, price/modality bounds) narrow the candidate list — never before — and only to the cheapest N candidates by blended price. If the filtered list still exceeds the cap, Anticharon never silently checks a subset and presents it as complete: it emits an explicit `ZDR_LIVE_LIMITED` warning message (§10.1a) naming how many of how many were checked, in both human and `--json` output, and proceeds with the cheapest N. `run`/`check --zdr` are unaffected by this cap — shortlists are inherently small (7–9 models typically), so the cap only matters for `discover`'s full-catalog case.

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
6. Standalone fallback: If not found in non-interactive/cron mode, emit a `HERMES_NOT_DETECTED` warning message (§10.1a) and fall back cleanly to `shortlist.json`. Standalone operation stays successful (`status: "success"` for `run`/`check`/`history`); the absence of the optional Hermes config is never an error, including for `model sync` / `import_hermes_models` (`status: "warning"`, exit 0).

### Two-Tier Safe Extraction Architecture:
- **Tier 1 (Hermes CLI):** If `hermes` binary is present on `$PATH`, queries `hermes config get model` and `hermes config get fallback_providers` directly (< 1.5s timeout).
  - `fallback_providers` output is accepted in **both** shapes the Hermes CLI may emit: an inline JSON array, and a raw YAML list (`- provider: openrouter` / `  model: <slug>`).
- **Tier 2 (Stream-Grep File Scanner):** Inspects the file using a line-by-line streaming regex scanner.
  - Matches `default: <model_slug>` (verified for OpenRouter provider).
  - Matches `fallback_providers: <json_array>` or multi-line YAML fallbacks.
  - The final fallback entry is retained whether the YAML block ends at EOF **or** is closed by a following top-level key (e.g. a `logging:` section).
  - Zero `pyyaml` dependency.
  - Constant memory footprint: reads line-by-line without buffering the file.
  - Zero secret leaks: API keys, system prompts, and tokens in other YAML sections are never read or stored.

### Detection Outcomes & Source Ordering:
Each source (Tier 1 CLI, Tier 2 file) resolves to exactly one of three outcomes:

| Outcome | Meaning |
| --- | --- |
| `complete` | A parseable default model **and** the complete fallback-model set were read. |
| `incomplete` | A model configuration demonstrably exists, but the complete set cannot be established (e.g. non-empty `fallback_providers` output that parses to zero entries, or a non-zero exit on the `fallback_providers` sub-query after the `model` sub-query already succeeded). |
| `unavailable` | The source cannot be read or queried at all — missing executable/file, timeout, non-zero exit, or equivalent access failure. |

**Tier 1 sub-query granularity (corrected, independent review):** the CLI tier issues two sub-queries (`hermes config get model`, then `hermes config get fallback_providers`). A non-zero exit on the *first* (`model`) sub-query makes the whole CLI source `unavailable` (no default model resolved at all — represented by `fetch_models_from_cli()` returning `None`). A non-zero exit on the *second* (`fallback_providers`) sub-query, after the default model already resolved, is `incomplete`, not `unavailable`: the configuration demonstrably exists (the default model was read successfully), but the complete fallback set could not be established. This is deliberately the same outcome as non-empty-but-unparseable `fallback_providers` output — both leave `fallback_models` empty while signaling `incomplete` rather than a silently "complete" default-only result. Only a genuinely empty, zero-exit `fallback_providers` query (`returncode == 0` and blank `stdout`) is the contractually intended fallback-less `complete` result.

The outcome is carried on the detection payload as the `detection` field (`"complete"` / `"incomplete"`); `unavailable` is represented by the absence of a payload. Source order is never reversed:

1. The Tier 1 CLI result is used when it is `complete`.
2. If the CLI result is `incomplete` or `unavailable`, Tier 2 (file) is tried.
3. A `complete` Tier 2 result is authoritative — it clears the incomplete CLI state entirely and emits **no** incomplete-detection warning (full recovery, not degraded fallback).
4. If neither tier reaches `complete`, the incomplete result is returned so callers can warn and protect the shortlist.

An `unavailable` source is **not** retried in-process; the next scheduled or manual invocation retries it.

### Sync Protection (applies to the final selected result, not per-tier):
- A `complete` final result is authoritative and **may** legitimately shrink, grow, or otherwise change the shortlist — a genuine change in Hermes's configured models must propagate, regardless of how its length compares to the persisted shortlist.
- An `incomplete` final result never overwrites an existing non-empty shortlist with the partial/default-only set it detected — **regardless of length**: shorter, the same length with different content, and even longer incomplete results are all rejected the same way. Length is not a reliable completeness signal for an `incomplete` detection (a corrected defect: an earlier revision of this guard only compared lengths, `len(new) < len(current)`, which let a same-length-but-different `incomplete` result silently overwrite a good shortlist — GH-4). The persisted shortlist is preserved unchanged and also drives the current tracking run.
- When the shortlist is preserved this way, a `HERMES_INCOMPLETE` warning message (§10.1a) is surfaced in human CLI output, in `--json` `messages` (`run`/`check`/`history`, and `model sync` alongside its `detection` field), and in the `import_hermes_models` MCP tool payload.
- Both sources `unavailable` is the ordinary no-Hermes case: existing configuration/standalone behavior is preserved, with a `HERMES_NOT_DETECTED` message rather than an incomplete-detection warning.
- `anticharon test` reports `[WARN]` (never an unqualified `[PASS]`) for the Hermes step when detection is `incomplete` or when the detected model set diverges from the persisted shortlist, exposing `detection` and `shortlist_divergence` in `--json` and a `HERMES_INCOMPLETE` / `HERMES_DIVERGENT` message.
- **Divergence (A2A-6, D-5):** one shared, order-sensitive check (`hermes_shortlist_divergent`) compares the detected Hermes sequence (default, then fallbacks) with only the persisted Hermes-sourced entries. Manual and other imported entries are excluded. A persisting `run` compares after its sync, so it reports `SHORTLIST_UPDATED` instead.

### Model Placement & Synchronization Rules:
- The Hermes `default` model is stored with `source: "hermes", order: 0`; OpenRouter fallback models follow with increasing `order`. This explicit default receives the `★ [DEFAULT]` badge and serves as the baseline for `BEST_OPTION_CHANGED` alerts.
- Manual entries survive Hermes synchronization. Their list position never implies a default.
- Newly discovered models are automatically initialized in `history.csv`/`effective_prices.json` using the cold-start & backfill rule (§3.5).
- User-configured weights (`weight_uncached_prompt`, `weight_cached_prompt`, `weight_completion`, `spike_threshold_pct`, `min_tracking_days_for_profile`) are preserved during synchronization.
- Upgrades/reinstallation resilience: If `~/.anticharon/` is deleted during an update, the next execution re-creates `~/.anticharon/shortlist.json` automatically.
- Opt-out: Pass `--no-hermes` to suppress Hermes auto-detection and run purely standalone.

---

## 3.6 Historical Analytical Intelligence & Pricing Profiles

Anticharon inspects the full 30-day temporal window stored in `history.csv` (`[d1..d7, d15, d30]`) and applies statistical dispersion analysis alongside live catalog sibling relationship tracking:

### Metric Definitions:

**Correction (PE2-009, 2026-09-17):** `N` below is the count of non-null observations actually present in the window (`src/anticharon/analytics.py`'s `calculate_model_analytics`, `len(all_prices)`), never a fixed `10` — an earlier revision of this section hardcoded `10`, which does not match the implementation and would silently misstate dispersion for any model with fewer or more valid observations (e.g. the single-observation golden case in §3, where the correct result is `CV = 0.0%` for `N = 1`, not division by `10`).

- **Mean Price:** `μ = sum(prices) / N`
- **Standard Deviation:** `σ = sqrt(sum((p - μ)²) / N)`
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

### v0.6.0 command split (D-19, MCP-11)
`run` is the **only** command that talks to OpenRouter. It writes `history.csv`,
`effective_prices.json`, and pre-computes + persists this run's alerts into
`alerts.json` (§5.3). `check` and `history` are both **local reads only** --
they make zero network calls, ever, and never recompute alerts:
- `check` = the latest normalized/blended price per model, from `history.csv`,
  plus the alerts `run` last persisted, shown verbatim.
- `history` = the long-term 30-day view over `effective_prices.json` (via
  `history.csv`'s already-derived `d1..d30`/MA columns) plus all analytics/
  profile classification, which lives here and not in `check`.

Both `check` and `history` report `DATA_STALE` when the latest locally stored
observation is older than today, pointing back to `run`.

### Primary Commands & Options:
```bash
# 1. Standard execution: fetch OpenRouter, persist history/effective_prices/alerts, print report
anticharon run
anticharon run --force        # re-fetch even if already updated today (same-day rule)
anticharon run --model "openai/gpt-5.6-luna"   # exact-filter the configured shortlist

# 2. Check: local read of the latest prices and persisted alerts (no network)
anticharon check
anticharon check --model "openai/gpt-5.6-luna"

# 3. Analytical Intelligence: Evaluate 30-day historical profiles and trajectory table (history only)
anticharon history --json
anticharon check --json

# 4. History Subcommand: Audit 30-day temporal metrics and export raw CSV
anticharon history
anticharon history --model "openai/gpt-5.6-luna"
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

# 15. Policy (ZDR) Pricing: calculate a separate ZDR-constrained `policy_price_1m` without replacing `effective_price_1m`
# --zdr exists only on `run` (D-28); it is a live-only, never-persisted addition to that response
anticharon run --zdr --json

# 16. Ergonomic Help Subcommand: Display top-level or subcommand usage
anticharon help
anticharon help run
anticharon help model
anticharon help model discover

# 17. User-initiated self-update operations (experimental)
anticharon check-updates [--json]
anticharon update --type install_only [--json]
# Numeric aliases 1–5 map to install_only, restart_host, phoenix,
# phoenix_inverted, and reload_request respectively.
```

`check-updates` uses GitHub Releases' `releases/latest` endpoint with a hard
two-second timeout. It reports `is_latest` only when the installed version
equals the release tag. It is user-initiated only: no background check, cache,
or update notice is added to unrelated command responses.

`update` is always **EXPERIMENTAL** and offers named sequences
`install_only`, `restart_host`, `phoenix`, `phoenix_inverted`, and
`reload_request`. Reinstallation prefers `uv tool install --force` from the
Git source; if `uv` is unavailable, it uses `sys.executable -m pip install
--force-reinstall`, never a bare `pip`. A successful reinstall may still need
a host restart. `phoenix` schedules the running server's termination for host
respawn; `phoenix_inverted` schedules termination before a detached reinstall;
`reload_request` asks the user to send `/reload-mcp`.

### JSON Output & Exit Codes
Every `--json` output uses the §10.1a envelope (`status`, `messages`, `elapsed_ms`, then the payload), and human output renders the same `messages`. The exit code is `1` iff `status` is `error` or `refused` (the operation was not performed), otherwise `0`. `model sync` without a detectable Hermes config is `status: "warning"` with `HERMES_NOT_DETECTED` and exits `0`.

---

## 8. Safety, Resilience & Network Fallback

1. **Timeout Control:** Every OpenRouter HTTP request has an explicit `10.0` second timeout.
2. **Self-Describing Fallback Schema:** If the OpenRouter API fails (HTTP error, connection reset, timeout), Anticharon reads `history.csv`, logs a non-fatal warning, and returns the last known prices. To prevent LLM agents from confusing HTTP cache fallbacks with model failover providers, the JSON schema includes explicit fields:
   - `data_source`: `"live_api"` (successful HTTP request) or `"cached_history"` (network failure fallback).
   - `api_offline_fallback`: `true` if OpenRouter API failed and local cache was used; `false` otherwise.
   - `fallback`: Legacy boolean alias for `api_offline_fallback` maintained for backward compatibility.
   - `_hints`: In-band field definitions dictionary included when `--hints` is passed.
   - `messages`: an `API_FALLBACK` warning message (§10.1a) states that cached prices are shown.
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
- **Protocol baseline:** MCP specification `2026-07-28` (https://modelcontextprotocol.io/specification/2026-07-28; schema `schema/2026-07-28/schema.ts` in `modelcontextprotocol/modelcontextprotocol`). Every protocol-shaped behavior (error signaling, annotations, `_meta`, tool naming) cites this revision; later revisions are adopted only through a sprint ledger's protocol-update check (`AGENTS.md` Rule 4).
- **SDK Implementation:** official Python SDK `mcp` (`pyproject.toml`: `mcp>=1.3.0`; resolves to `mcp` 2.x `MCPServer`, with `FastMCP` only as an import fallback).

### 10.1a Response Envelope & Agent Messages (CLI `--json` and MCP)

One contract for every JSON payload: every MCP tool result and every CLI `--json` output (`run`, `check`, `history`, `info`, `test`, `calibrate`, `check-updates`, `update`, `model add|remove|list|discover|sync`). Raw CSV outputs (`--history-csv`, `history --csv`) are not JSON and are unchanged.

- **Top-level keys, in this order:** `status`, `messages`, `elapsed_ms`, then the payload.
- **`status`:** `success` · `warning` (done, with problems worth flagging) · `error` · `refused` · `not_monitored`. A target absent from the shortlist is `refused` (with a `NOT_MONITORED` message) only for a filtered *live* operation (`run --model`/`run_prices(model_id)`), which makes no catalog or price request for it; on a local read (`check`/`check_prices`, `history`/`get_model_history`) the same absent-target case is `status: "not_monitored"` — a normal result, not an error. `status` is set by the operation, not derived from message levels: a `warning`-level message can accompany `status: "success"` (e.g. standalone mode).
- **Error signaling (MCP spec 2026-07-28, Tools → Error Handling):** `status` ∈ {`error`, `refused`} means the requested operation was not performed. MCP returns it as a tool execution error (`isError: true`) whose text content and `structuredContent` are the same JSON envelope, so hosts pass it to the model for self-correction; the CLI exits with code `1`. Every other status, including `not_monitored`, is a normal result (exit `0`).
- **`messages`:** never empty. Each entry is an `AgentMessage` (`models.py`): `level` (`info` | `warning` | `error`), `code` (stable string), `text` (one human sentence), optional `action` (`{"mcp": "<tool call>", "cli": "<command>"}`), optional `model` (slug, per-model messages only). Problem and outcome messages come first; the last entry is always `COMPLETED` (`info`), timed from the start of the command/tool call ("Anticharon processed your request successfully in 0.4s."; for `error`/`refused` it says the request was not performed).
- **`elapsed_ms`:** integer wall-clock milliseconds for the command/tool call.
- **Human CLI output** renders the same serialized `messages` through one renderer (`render_messages`): `<icon> [CODE] text`, followed by `↳ <cli action>` when present. In MCP mode nothing is rendered to `stdout` (stdio isolation, ADR 0001).
- **Removed legacy keys (clean break, 0.6.0):** `notice`, `hint`, top-level `message`, `hermes_integration.warning`, `model sync` `warning`, top-level `error`, and discover's `zdr_warning`. `priceWarnings` is renamed `price_warnings`. Kept as data: `status`, `_hints`, `price_warnings[].message`, and per-check `error` fields in `anticharon test`.
- **`_meta`** is never the agent channel; messages are not mirrored into `_meta`.

Codes emitted in 0.6.0 so far (the full catalog, including codes introduced by later work, is ledger `docs/plans/ecosystem-ergonomics/EXECUTION_CONTRACT.md` §3d):

| Code | Level | Emitted by | Meaning / action |
|---|---|---|---|
| `COMPLETED` | info | every command/tool | always last; elapsed time |
| `PREVIEW_ONLY` | info | any dry run (`check`, `history`, `run --dry-run`, `check_prices`, `get_model_history`, `model add/remove/sync --dry-run`, `calibrate --dry-run`, `import_hermes_models`) | work done for this response only; nothing persisted → repeat without dry run |
| `SHORTLIST_UPDATED` / `SHORTLIST_UNCHANGED` | info (`SHORTLIST_UNCHANGED` is `warning` for a duplicate `model add`, `error` for `model remove` of an absent slug) | persisting `run`/default command (Hermes sync), `model sync`/`import_hermes_models`, `model add/remove`, `calibrate` | what was persisted to `shortlist.json` |
| `NO_EXACT_MATCH` | error (`refused`) on `model add`; warning (per model) on `run` | exact catalog validation or a shortlist slug absent from the live catalog | no prefix substitution; add refuses an invalid catalog slug and `run` skips the unmatched shortlisted slug → `discover_models` |
| `CATALOG_UNAVAILABLE` | error | `model add` | catalog could not be queried; nothing is added → retry later |
| `NOT_MONITORED` | warning on local reads (`status: "not_monitored"`); error (`refused`) on a filtered live `run` | `run --model` (`refused`); `check --model`/`check_prices`, `history --model`/`get_model_history` (`not_monitored`) | slug is absent from shortlist; no catalog or price request is made → add the model explicitly |
| `PRICE_UNAVAILABLE` / `PRICE_INVALID` | warning (per model) | `run` | model has no usable advertised price or its listed price is invalid; that model is skipped with an explicit reason |
| `NO_DEFAULT` | info | `run`, local price views | no explicit `order: 0` entry; no default-based alert is produced |
| `SOURCE_MANAGED` | error (`refused`) | `model remove`, manual default while Hermes owns the default | edit the owning source instead; Anticharon never writes to Hermes |
| `API_FALLBACK` | warning | `run`/`run_prices` only | OpenRouter unreachable; cached `history.csv` prices shown. `check`/`history` never call OpenRouter, so they cannot emit this code (§10.2 v0.6.0 command split) |
| `DATA_STALE` | warning | `check`/`check_prices`, `history`/`get_model_history` | the latest locally stored price observation (across the models shown) is older than today → `run`/`run_prices` |
| `HERMES_NOT_DETECTED` | warning | `run`, `check`, `history`, `check_prices`, `get_model_history`, `model sync`, `import_hermes_models` | no Hermes config found; standalone operation stays successful → pass a Hermes config path / `$HERMES_CONFIG`, or `--no-hermes` |
| `HERMES_INCOMPLETE` | warning | same as above, and `test` | partial detection; shortlist protected (§6.2) |
| `HERMES_DIVERGENT` | warning | `run`, `check`, `history`, `check_prices`, `get_model_history`, `test` | Hermes sequence ≠ persisted shortlist, order-sensitive (§6.2) → `import_hermes_models(dry_run=false)` / `anticharon model sync` |
| `SELF_TEST_FAILED` | error | `test` | one or more checks failed (`status: "error"`, exit 1); per-check `error` fields carry causes |
| `CALIBRATION_INPUT_INVALID` | error | `calibrate` | activity CSV missing, unreadable or unparseable; weights unchanged (`status: "error"`, exit 1). Only invalid/unreadable input uses this code; other exceptions are internal failures and are not reported as invalid input |
| `ZDR_LIVE_LIMITED` | warning | `model discover --zdr` | live ZDR results are limited: check capped at `max_zdr_check_count` (how many of how many) and/or compliance unknown for named models |
| `UP_TO_DATE` / `UPDATE_AVAILABLE` | info | `check-updates` / `check_updates` | installed version equals / differs from GitHub's latest release; the latter points to `run_update` |
| `UPDATE_CHECK_FAILED` | error | `check-updates` / `check_updates` | GitHub check failed within the hard timeout (`status: error`, MCP `isError: true`) |
| `EXPERIMENTAL` | warning | `update` / `run_update` | always present: update may require manual intervention |
| `UPDATE_INSTALLED` / `UPDATE_FAILED` | info / error | `update` / `run_update` | reinstall command outcome |
| `RESTART_REQUIRED` | warning | `update` / `run_update` | updated process requires host restart, respawn, or `/reload-mcp` |

### 10.2 Exposed MCP Tools

#### 1. `check_prices` (D-19: local read, no network)
- **Description:** Local read of the latest normalized/blended price per the monitored shortlist from `history.csv`, plus the price alerts (PRICE_SPIKE, PRICE_DROP, BEST_OPTION_CHANGED) persisted by the last `run_prices` call in `alerts.json` -- shown verbatim, never recomputed. Makes no OpenRouter network call; `readOnlyHint: true`, `openWorldHint: false`.
- **Parameters:**
  - `model_id` (string, optional): Exact shortlisted slug to read. If omitted, returns all shortlisted models. An absent slug returns `status: "not_monitored"` with `NOT_MONITORED` (a normal result, not `isError`; no catalog lookup).
- **Return Payload:** The §10.1a envelope (`status`, `messages`, `elapsed_ms`) followed by `timestamp`, `data_source` (always `"cached_history"` -- this tool never performs a live call), `api_offline_fallback`, `prices_shortlist` (each entry carrying `effective_price_1m` and `advertised_prompt_1m`/`advertised_completion_1m`; no `policy_price_1m` -- ZDR is live-only, `run_prices`-only, D-28), `price_warnings` (as persisted), `hermes_integration` (`detected`, `source`, `method`, `models_count`), and in-band `_hints`. A `DATA_STALE` warning is added when the latest locally stored observation is older than today.

#### 2. `run_prices` (D-19: the only fetch-and-persist tool)
- **Description:** Fetches current OpenRouter model pricing for the monitored shortlist, calculates the cache-aware advertised/effective/policy price triple (§3.1), writes `history.csv` and `effective_prices.json`, and pre-computes + persists this run's price alerts into `alerts.json` (§5.3). Saves by default (D-29); `readOnlyHint: false`, `openWorldHint: true`.
- **Parameters:**
  - `model_id` (string, optional): Exact-filter the configured shortlist to one model (D-18c). An absent slug is refused as `NOT_MONITORED` with no catalog lookup or pricing request.
  - `dry_run` (boolean, optional, default: `false`): Compute the full update without persisting anything (D-18b).
  - `force` (boolean, optional, default: `false`): Re-fetch a model even if it was already updated today (same-day rule, D-3/D-18).
  - `zdr_only` (boolean, optional, default: `false`): Add a policy-constrained `policy_price_1m` from Zero Data Retention-compliant endpoints (§3.2) and surface `POLICY_UNROUTABLE`/`POLICY_UNKNOWN` warnings for this response only -- never persisted to `alerts.json` (D-28).
- **Return Payload:** Same shape as `check_prices` above, plus `data_source` reflecting the live call (`"live_api"` or `"cached_history"` on API failure) and, when `zdr_only` is set, `policy_price_1m`/`is_policy_routable` per model.

#### v0.6.0 exact shortlist selection contract (D-14, D-18c)

`run` fetches prices for the configured shortlist. `run --model X` and its MCP
equivalent `run_prices(model_id=X)` are exact filters over that shortlist. If
X exactly matches a configured entry, only that model is fetched and persisted.
If X is absent, the operation returns `status: "refused"` with a
`NOT_MONITORED` message, MCP `isError: true` (or a nonzero CLI exit), and makes
no catalog lookup or pricing request for X. Prefix and similar-slug matching
are prohibited.

Local `check` and `history` operations also make no network calls; an absent
shortlist slug is reported as `status: "not_monitored"` with a `NOT_MONITORED`
message -- a normal result (exit `0`, not MCP `isError`), unlike the `refused`
result above for a filtered *live* `run`. `add_model` is the separate
network-backed catalog validation operation. It accepts only an exact catalog
slug, returns `NO_EXACT_MATCH` for an invalid or nonexistent slug, and reports
`CATALOG_UNAVAILABLE` when the catalog cannot be checked.

#### 3. `get_model_history` (D-19: local read, no network)
- **Description:** Local read of 30-day temporal price history, volatility coefficient of variation (CV%), directional trends, and deterministic intelligence profiles (STABLE, PROMO_ENDED, SUNSETTING, VOLATILE, DISCOUNTED, CREEPING_INFLATION, NEWLY_TRACKED), derived from `history.csv`'s `d1..d30` columns (themselves derived from `effective_prices.json` by the last `run_prices` call, §5.2). All analytics/profile classification lives in this tool, not in `check_prices`. Makes no OpenRouter network call; `readOnlyHint: true`, `openWorldHint: false`.
- **Parameters:**
  - `model_id` (string, optional): Exact shortlisted slug to inspect. If omitted, returns all shortlisted models. An absent slug returns `status: "not_monitored"` with `NOT_MONITORED` (a normal result, not `isError`).
  - `format` (string, optional, default: `"json"`): Output format (`"json"` for structured analytics or `"csv"` for raw historical table).
- A `DATA_STALE` warning is added when the latest locally stored observation is older than today.

#### 4. `discover_models`
- **Description:** Queries and filters OpenRouter's live catalog (~417+ models) using multi-criteria keyword matching, promotional status, output modality, and price ceiling expressions, calculating real-world blended prices calibrated to user token weights.
- **Parameters:**
  - `query` (string, optional): Search query (e.g. `"gemini"`, `"qwen"`).
  - `promo_only` (boolean, optional, default: `false`): Filter for promotional or free models (:free, $0.00).
  - `modality` (string, optional, default: `"text"`): Modality filter (e.g. `"text"`).
  - `max_price` (number, optional): Maximum blended price per 1M tokens ($).
  - `limit` (integer, optional, default: `15`): Maximum number of matching models to return.

#### 5. `import_hermes_models`
- **Description:** Imports active default and fallback models from Hermes Agent configuration (`~/.hermes/config.yaml` or `$HERMES_HOME`) into Anticharon's shortlist. **Strictly read-only on Hermes**: never modifies Hermes configuration.
- **Parameters:**
  - `hermes_config_path` (string, optional): Explicit custom path to Hermes `config.yaml`.
  - `dry_run` (boolean, optional, default: `false`): Saves the import to Anticharon's `shortlist.json` by default. When `true`, detects and returns Hermes models without modifying disk.
- **Response Safety Fields:**
  - `direction` (`"hermes→anticharon"`): Confirms one-way data flow.
  - `hermes_untouched` (`true`): Confirms Hermes configuration was not mutated.
  - `messages` (§10.1a): `PREVIEW_ONLY` / `SHORTLIST_UPDATED` / `SHORTLIST_UNCHANGED` state preview vs persistence; `HERMES_INCOMPLETE` flags a protected shortlist; `HERMES_NOT_DETECTED` (with `status: "warning"`, never an error) when no Hermes config is found.
  - CLI `model sync` / `model import-hermes --json` returns the same payload and messages (one shared builder).

#### 6. `check_updates` and `run_update` (experimental self-update)

- `check_updates()` compares `anticharon.__version__` with GitHub Releases'
  latest release using a hard two-second timeout. It is read-only, open-world,
  idempotent, and returns `is_latest`. A failure returns `UPDATE_CHECK_FAILED`
  with `status: error` and MCP `isError: true`.
- `run_update(type="install_only")` is the only Anticharon tool that executes
  commands. It is experimental, destructive, non-idempotent, and open-world.
  The named enum is `install_only`, `restart_host`, `phoenix`,
  `phoenix_inverted`, and `reload_request`; every response includes the
  `EXPERIMENTAL` warning. It prefers `uv tool install --force` from the Git
  source and otherwise invokes `sys.executable -m pip install --force-reinstall`.
  The Phoenix variants schedule server termination for host respawn; a caller
  must explicitly request them.

### 10.3 Exposed MCP Resources
- `anticharon://llms.txt`: Machine-readable Agent-to-Agent operational briefing and schema definitions. The repository-root `llms.txt` is the only source; Hatch's wheel `force-include` maps it to `anticharon/llms.txt`.
- `anticharon://history.csv`: Raw 30-day sliding history table (`model,last_updated,effective_price_1m,advertised_prompt_1m,advertised_completion_1m,ma_3d,ma_7d,d1..d7,d15,d30`).
- `anticharon://shortlist.json`: Active model shortlist and token weight configuration.
- `anticharon://calibration-details`: Definitions and derivation guidance for the three token weights, sample values, the server-local CSV workflow, and the local CLI fallback.

### 10.4 Exposed MCP Prompts
- `cost_spike_triage`: Prompt template guiding an agent to analyze a detected `PRICE_SPIKE` or `PROMO_ENDED` alert and formulate model switching recommendations.
- `model_migration_advisor`: Prompt template guiding migration from a `SUNSETTING` model to an equal or cheaper sibling alternative.
- `family_upgrade_discover`: Discovers newer generation models in the same provider family (e.g. Gemini, DeepSeek, Qwen) and evaluates cost-benefit migration.
- `daily_cost_briefing`: Generates an executive daily cost briefing of model prices, moving averages, and volatility alerts across the active shortlist.
- `budget_optimization_audit`: Audits the active shortlist to identify cost outliers, SUNSETTING legacy versions, and opportunities to reorder fallback providers.

The five prompt templates are single-sourced in `anticharon.prompts` and are exposed by MCP and `anticharon prompt`. Running `anticharon prompt` lists names and descriptions; `anticharon prompt <name> --arg KEY=VALUE` renders one prompt.

### 10.6 W4 MCP tools and calibration

- Every MCP tool description links to `anticharon://llms.txt` as the authoritative glossary.
- `add_model(model_id, dry_run=false, default=false)` and `remove_model(model_id, dry_run=false)` use the same shortlist manager as the CLI and save by default. `dry_run=true` performs validation/calculation without saving. `add_model` requires an exact live catalog match; when the catalog is unavailable it returns `CATALOG_UNAVAILABLE` and does not persist. `list_models()` is a local read. `self_test()` runs the same checks as `anticharon test`, including Hermes integration, captures its JSON report without writing to MCP stdout, and reports `SELF_TEST_FAILED` on failure.
- `calibrate_token_weights(csv_path, dry_run=false)` reads a server-local activity CSV; CSV bytes are not transported over MCP. `calibrate_fast(weight_uncached_prompt, weight_cached_prompt, weight_completion, dry_run=false)` accepts host-derived values. Both write by default and copy the prior configuration to the sibling `.bak` file before mutation, reporting `CALIBRATION_BACKUP`; dry runs do not write.
- `calibrate_fast` validates finite numeric values in `[0, 1]`, requires a sum within `0.000001` of 1, normalizes by that sum, and rounds each normalized value to six decimals.
- `anticharon://calibration-details` documents weight meanings, a sample derivation, and the CLI fallback for CSV files unavailable to the MCP server.
- Every registered MCP tool declares all five `ToolAnnotations` fields (`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) according to its worst-case behavior in §3b and the MCP-9 table. Server initialization sets `version` to the package version and provides operational instructions.

### 10.5 Host Configuration Integration

Supported persistent install modes are `uv tool install git+https://github.com/parisneto/anticharon.git` and `pip install git+https://github.com/parisneto/anticharon.git`. A contributor checkout may run `uv run --directory $HOME/src/anticharon anticharon mcp`. Users inspect a persistent install with `check_updates`; `run_update` is experimental and may require a host restart.

#### Hermes Agent (`~/.hermes/config.yaml`):
```yaml
mcp_servers:
  anticharon:
    command: "~/.local/bin/anticharon"
    args: ["mcp"]
```

#### Claude Desktop (`claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "anticharon": {
      "command": "$HOME/.local/bin/anticharon",
      "args": ["mcp"]
    }
  }
}
```

Hermes expands `~`. Expansion of `$HOME` in other host configuration files is
pending E-2 host-install verification; configure the resolved installed-binary
path if the host does not expand it.

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
