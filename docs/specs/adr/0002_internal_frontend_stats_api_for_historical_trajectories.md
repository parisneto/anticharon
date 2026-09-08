# ADR 0002: Ingestion of Internal Frontend Stats API for Historical Trajectories & Day 1 Cold-Start Bootstrapping

## Status
Accepted

## Date
2026-09-05

## Context
Anticharon calculates 30-day statistical pricing dispersion (Coefficient of Variation, 30-day baseline delta, and behavioral profile tags such as `STABLE`, `VOLATILE`, `PROMO_ENDED`, `SUNSETTING`, `DISCOUNTED`).

In earlier versions (v0.1.0 to v0.2.1), Anticharon operated purely as a **passive daily accumulator**:
1. When tracking a new model, `history.csv` required up to 30 days of cron runs (`anticharon run`) to build the historical time-series (`[d1..d7, d15, d30]`).
2. On Day 1, newly shortlisted models had identical observations across all slots, forcing a default `NEWLY_TRACKED` classification.
3. If an orchestrator (e.g. Hermes Agent) added a new model, it could not immediately evaluate whether the model was currently on promotion or suffered recent price spikes.

Investigation of OpenRouter's web interface revealed two unadvertised, unauthenticated frontend statistics endpoints:
- `GET https://openrouter.ai/api/frontend/v1/stats/effective-pricing?permaslug={canonical_slug}&range={range}&shape=v7&variant=standard`
- `GET https://openrouter.ai/api/frontend/v1/stats/listed-pricing?permaslug={canonical_slug}&range={range}&shape=v5&variant=standard`

These endpoints accept `permaslug` (the date-stamped canonical slug, e.g. `openai/gpt-5.6-luna-20260709`) and a time-window parameter `range` (`3d`, `1w`, `1m`, `3m`, `1y`, `all`). With `range=1m`, OpenRouter returns up to 32 daily records with unrounded float precision per provider endpoint, factoring in prompt-caching discounts.

## Decision

### 1. Adopt `effective-pricing` (`shape=v7&range=1m`) as the Historical Bootstrapper
We decided to integrate `effective-pricing` to eliminate the 30-day cold-start latency:
- **Instant Day 1 Intelligence:** When a new model is shortlisted, Anticharon bootstraps its past 30-day trajectory immediately, providing instant behavioral profile classification (`STABLE`, `DISCOUNTED`, etc.).
- **Headless & Zero-Auth:** The endpoint requires no cookies, headers, Playwright, or GPU. It executes in pure Python standard library (`urllib.request` + `json`) in <200ms.

### 2. Dual-Tier Storage Architecture
To avoid bloat while preserving deep analytical capability, Anticharon maintains two synchronized stores:
- **`history.csv` (Compact Sliding Window):** Preserved for fast daily cron execution, moving average calculations (`ma_3d`, `ma_7d`), and backward compatibility with lightweight CLI subcommands.
- **`fullhistory.csv` (Granular Multi-Provider Time-Series):** Persists date, provider endpoint ID, provider name, token flow (`input` / `output`), effective price, and weighted model benchmarks.

### 3. Smart Triggering Policy (Zero Network Waste)
To prevent rate limits and respect external services:
- **Routine Fast Checks (`anticharon check`):** Continue to use the official single-model REST endpoint (`GET /api/v1/models/{slug}`) with hard 10s timeouts (<100ms).
- **Full History Synchronization is Fired Selectively ONLY When:**
  1. A price spike is detected (`PRICE_SPIKE` ≥ +20%).
  2. Local historical data is stale (data liveness `STALE` > 7 days without sync).
  3. The user or agent explicitly invokes `anticharon sync --full`.

### 4. Resilient Fallback & Degradation Contract
Because `/api/frontend/v1/stats/` is an internal OpenRouter frontend route without a formal public SLA:
- **Strict Isolation:** Any HTTP failure, timeout, or schema change on this endpoint is non-fatal.
- **Graceful Degradation:** The engine catches exceptions, logs a notice to `stderr`, and falls back to existing `history.csv` observations without crashing Hermes Agent or cron jobs.
- **Event Audit Stream (`listed-pricing`):** Evaluated as an asynchronous tariff revision log, reserved for event-driven price audit features.

## Consequences

### Positive
- Completely eliminates the 30-day cold-start delay for newly tracked models.
- Provides true 30-day empirical evidence across multiple competing provider endpoints.
- Requires zero heavy scraping frameworks (no Selenium, Chromium, or Playwright).

### Negative / Trade-offs
- Internal endpoint paths (`/api/frontend/v1/stats/...`) or schema shapes (`shape=v7`) could change during major OpenRouter frontend redesigns; requires resilient try/except encapsulation and fallback tests.
- Models requiring router slugs (e.g. `~deepseek/deepseek-v4-flash-latest`) must resolve to their active underlying canonical release slug before querying stats.
