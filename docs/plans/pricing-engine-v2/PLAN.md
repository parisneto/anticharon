# PLAN.md — Pricing Engine v2 (Cache-Aware + Provider-Routable + 28-Day Backfill)

> Long-form plan behind `EXECUTION_CONTRACT.md` (authoritative TL;DR — this document must not contradict it; where something below is not yet settled, it is marked **OPEN** rather than guessed).
>
> Revision 2 (2026-09-15): incorporates decisions made after the first draft — dual-source/dual-file backfill, corrected advertised-vs-blended pricing semantics, the same-day-rerun bug, and answers to all six original divergences. Superseded text from revision 1 has been replaced, not appended.

## Context

Anticharon's tracked price has always come from OpenRouter's bulk `/api/v1/models` headline `pricing.prompt`/`pricing.completion` fields, fed into a 2-component gross formula (`P_in × w_prompt + P_out × w_completion`). Two independent, evidence-backed defects were found in this:

1. **Cache blindness.** `src/anticharon/log_parser.py` never reads `tokens_cached` from activity logs. Comparing two real exports (`docs/sample/openrouter_activity_2026-08-24.csv`, `docs/sample/openrouter_activity_2026-09-15.csv`) shows 75–82% of prompt tokens served from cache, cutting real cost 59–66%. The gross formula overestimates real cost by 55–75% for cache-heavy agents (see `ADR_CANDIDATE_TOKENS_CACHED.md` Golden Cases #1–#3, #5).
2. **Provider-routability blindness.** The headline price is whichever provider OpenRouter lists, which may not be routable under an account policy (Zero Data Retention being the concrete, verified case). For `openai/gpt-5.6-sol`: listed $2/$10 per 1M, but under ZDR only Azure endpoints are routable at $5–$5.50 in / $30–$33 out (+150–200%). A live-captured `/models/{slug}/endpoints` payload confirms this via a real `status` field (`-2` = retention-blocked, `0` = routable) and confirms `pricing.input_cache_read`/`input_cache_write` are available per-endpoint from the same public, unauthenticated call — no internal/undocumented endpoint is needed for either of these two data points.

Both defects mean `history.csv`, moving averages, spike/drop alerts, and 30-day analytics have been computed on a price nobody actually pays. Per `EXECUTION_CONTRACT.md`, this is being fixed as one unified initiative — the legacy 2-component formula is **removed**, not kept behind a flag.

A third concern is pulled into this same initiative per `EXECUTION_CONTRACT.md` §1: **28-day historical backfill** on first tracking a new model, so cold-start doesn't mean 30 days of fabricated flat padding (this was originally ADR 0002's whole scope; it is now one golden case / acceptance-criteria group here, not its own feature).

## Core pricing semantics (locked 2026-09-15)

This resolves an earlier ambiguity — worth stating precisely since it's foundational:

- **"Blended price" is one concept, always 3-component.** `Price = (P_uncached × w_uncached) + (P_cache_read × w_cached) + (P_out × w_completion)`. There is no second, cache-blind "blended" number anywhere in the system, calibrated or not. Any code path that still does a 2-component blend after this change is a bug.
- **"Advertised" is never blended, and never pinned to whichever endpoint wins.** It's the raw listed reference from the bulk catalog headline, stored as a pair — `advertised_prompt_1m`, `advertised_completion_1m` — regardless of which specific endpoint `effective_price_1m`/`policy_price_1m` end up routing through. Which endpoint OpenRouter actually serves a request from is OpenRouter's routing decision, not Anticharon's — Anticharon only surfaces the shortlist and highlights how routing can impact or benefit real cost; it never decides or reroutes on the agent's/user's behalf (see Non-Goals: no dynamic rerouting). `advertised` exists purely as a transparency/comparison anchor, not as an input to any calculation.
- **`effective_price_1m`** (replaces `current_price_1m` as the canonical tracked number — kept as a legacy-named alias field during transition if that helps downstream code, **OPEN**: confirm whether to rename outright or alias) is the 3-component blend computed against the cheapest endpoint's real pricing.
- **`policy_price_1m`** (optional) is the same 3-component blend, restricted to endpoints passing an active policy filter (ZDR to start).
- **Calibrated users** get `(w_uncached, w_cached, w_completion)` from `anticharon calibrate` against real activity logs (now reading `tokens_cached`).
- **Non-calibrated users (default/cold-start)** currently get `weight_prompt=0.9971 / weight_completion=0.0029` from the TraceLab paper citation in `config.py`. That default now needs a third number — a default cache-hit-rate — which no equivalent public paper covers. Per your instruction, use what we actually have: pooling the two real activity-log samples in `docs/sample/` (`70,516,104` cached tokens over `91,973,374` total prompt tokens across both files) gives an interim default **cache-hit-rate ≈ 0.7667**. Decompose the existing default: `w_cached = 0.9971 × 0.7667 ≈ 0.7645`, `w_uncached = 0.9971 × (1 − 0.7667) ≈ 0.2326`, `w_completion = 0.0029` (unchanged). **Backlog task added** (see Deferred below): find a public/documented source for a better default cache-hit-rate assumption, same as TraceLab justified the existing prompt/completion split — this interim number is admittedly just "what we happened to observe in two personal exports," not independently validated.

## Storage architecture (revised — two files, two lifecycles)

Per your direction, replacing the single-file "add one column" idea from revision 1:

**`history.csv` (compact, fast-read, unchanged row-per-model shape):**
- `model,last_updated,effective_price_1m,advertised_prompt_1m,advertised_completion_1m,ma_3d,ma_7d,d1..d7,d15,d30`
- `ma_3d`/`ma_7d`/`d1..d7,d15,d30` are now **precalculated from the granular effective-pricing store** each sync (see below), not accumulated by shifting one slot per run. This directly fixes the historical inaccuracy problem, not just the cache-blindness problem.
- **Same-day-rerun bug fix (your catch):** current `tracker.py` does `new_prices = [current_1m] + prev_prices[:8]` unconditionally on every run — no check against `last_updated`'s calendar date, so running `anticharon run` twice in one day silently corrupts the `d1..d7` window (each run counts as a full day-shift). Fix: only shift the window when `last_updated`'s date differs from today's; a same-day rerun updates today's slot in place. This is being fixed as part of this same storage rework since it touches identical code.
- Nullable slots: empty string = "no real observation yet," not a fabricated duplicate of the current price (unchanged from revision 1's plan, still correct).

**New granular JSON store (`data/effective_pricing.json` or similar — exact name/path **OPEN**, follows the same path-resolution hierarchy as `history.csv`):**
- Per-model, per-provider daily time series pulled from OpenRouter's internal `effective-pricing` route: date, provider, effective price (cache/volume-weighted), listed price, cache hit rate, token share where available.
- Its own staleness/refresh policy, independent of `history.csv`'s per-run cadence — e.g. refresh only when data is older than N hours/days, not on every `anticharon run`. Exact cadence **OPEN**.
- `history.csv`'s precalculated stats are *derived from* this file, not the other way around — this file is the source of truth for history, `history.csv` is a fast-read cache of summary stats over it.

## 28-Day Backfill — decided: use both sources, cross-validate

On first sync for a model, fetch **both**:
1. The public bulk `/models` catalog (or `/models/{slug}/endpoints`) — gives today's listed price, used for `advertised_prompt_1m`/`advertised_completion_1m`.
2. The internal `effective-pricing` route — gives up to ~30 days of real daily observations, used to populate both the granular JSON store and to precalculate `history.csv`'s `d1..d7,d15,d30`/MA columns.

**Gated cross-validation test:** the "listed" baseline reported by the internal effective-pricing route should match the public catalog's listed price for the same model on the same day. Assert this in a test (`@pytest.mark.live`, since it needs the real API) — if they diverge, that's an early-warning canary that one of the two endpoints changed shape or semantics.

Graceful degradation: if the internal route fails or its shape has changed, fall back to the same no-fabrication rule as before (store only what the public snapshot gives you — today's single point — rather than fabricating history), exactly like every other network call in this codebase already does.

## Data Model Changes

**`src/anticharon/models.py`:**
- `PromptMixResult` gains `total_cached_tokens`, `total_uncached_tokens`, `weight_uncached_prompt`, `weight_cached_prompt`, `weight_completion`, `cache_hit_rate`.
- New `PricePoint` dataclass: `advertised_prompt_1m: float`, `advertised_completion_1m: float`, `effective_price_1m: float`, `policy_price_1m: Optional[float]`, `is_policy_routable: Optional[bool]`, `cache_hit_rate_used: float`.
- `ModelPrice` gains `price: PricePoint`.
- `PriceRecord.prices: List[Optional[float]]` — nullable slots.
- `PriceWarning` gains `POLICY_UNROUTABLE` (message + policy name + excluded providers + reason).

**`src/anticharon/analytics.py` (`calculate_model_analytics`):**
- Rework to compute mean/CV/profile only over non-null slots actually present; `NEWLY_TRACKED` means "fewer than N real observations," not "fewer than 28 days elapsed." **OPEN**: exact minimum N for a non-`NEWLY_TRACKED` classification (1 point is confirmed `NEWLY_TRACKED` per the Execution Contract's own golden case; the floor for `STABLE`/`VOLATILE` etc. isn't specified yet).

## Module-by-module implementation

- **`log_parser.py`:** read `tokens_cached`; compute uncached/cached/completion weights + cache-hit-rate per the ADR formula.
- **`config.py`:** default config's `weight_prompt`/`weight_completion` decomposed into the 3-way default described above; add the pooled cache-hit-rate constant with a comment citing its provisional/interim status.
- **`tracker.py`:** fetch bulk catalog (advertised price/metadata) + `/models/{slug}/endpoints` (effective/policy price) + internal effective-pricing route (backfill, on first sight of a model or per the JSON store's own staleness policy). Apply the same-day-rerun guard.
- **`discovery.py`:** add `zdr_only: bool = False` to `fetch_catalog()`.
- **`cli.py` / `mcp.py`:** surface `advertised` / `effective` / `policy` (when active) as three distinct, clearly-labeled numbers everywhere a price is shown — never collapse them back into one.

## Testing (per `EXECUTION_CONTRACT.md` §2)

- Adopt `pytest`; retire `tests/run_tests.py` outright as the CI gate (confirmed — no transition period). `anticharon test` (the user-facing diagnostic command) is unaffected.
- Structure: `conftest.py`, `fixtures/` (sanitized real JSON payloads — the live-captured endpoints payload referenced in `ADR_CANDIDATE_TOKENS_CACHED.md` is a strong starting fixture), `test_log_parser.py`, `test_tracker.py`, `test_policy_pricing.py`, `test_golden_pricing.py` (the 5 golden cases, verbatim), `test_analytics.py`, `test_effective_pricing_backfill.py` (includes the cross-validation canary, `@pytest.mark.live`).
- Categories per the contract: unit, fixture-based parsing, mocked integration, failure-path (timeout test stays here only, scoped honestly), `@pytest.mark.live` (excluded from default `uv run pytest`).

## Docs / spec / changelog / version

- `docs/specs/spec_v1_anticharon.md`: new section replacing the current single-price framing with the three-price model + dual storage.
- `AGENTS.md`: amend Rule 8 (pytest adoption) and Rule 4 (add `docs/plans/<initiative>/` as a documented convention — confirmed, see below).
- `CHANGELOG.md`: MINOR bump to `v0.5.0`, with an explicit callout that historical `history.csv` values now mean something semantically different even though the file format is backward-compatible.
- `docs/BACKLOG.md`: confirmed OK to edit — collapse the two currently-staged separate items (historical backfill, ZDR/super-discovery) into one "Pricing Engine v2" entry pointing at this plan folder.

## Explicitly paused / non-goals (unchanged)

- No auto-suggest-replacement-model / fallback-search feature (`search_by_tokens` and friends) — paused, insufficient data/logic maturity.
- No dynamic real-time provider rerouting inside agent sessions.
- No `pricing.overrides` (long-context tiers) or `pricing.discount` modeling this pass.
- No OpenRouter dashboard parity.

## Deferred / future backlog tasks surfaced by this round

- Find a public/documented source for a better default cache-hit-rate assumption (current interim default is derived from two personal log exports only).
- Revisit whether `status` values other than `-2`/`0` (e.g. `-5`, observed but unexplained in the live payload) need distinct handling.
- `pricing.overrides` (long-context pricing tiers) and `pricing.discount` — noted, not modeled yet.

---

## Resolved divergences (all six from revision 1)

1. **`advertised_price_1m` column** — resolved: stored as a raw pair (`advertised_prompt_1m`/`advertised_completion_1m`), never blended. See "Core pricing semantics" above.
2. **28-day backfill data source** — resolved: use both public and internal sources, cross-validated.
3. **Policy flag naming** — proceeding with `--zdr` (no objection raised).
4. **Retiring `tests/run_tests.py`** — resolved: retire outright.
5. **`docs/plans/<initiative>/` convention** — resolved: yes, document in AGENTS.md Rule 4.
6. **`docs/BACKLOG.md` reconciliation** — resolved: approved, collapse to one entry.

## Verification

1. `uv run pytest` (default gate) — deterministic, no network, fast.
2. `uv run pytest -m live` — validates real API contracts, including the advertised-vs-effective-pricing cross-validation canary.
3. `uv run anticharon test` — diagnostic self-check still green.
4. Manual: `uv run anticharon check --dry-run --json` shows advertised/effective (and policy, with `--zdr`) as three distinct numbers for a known cache-heavy model; reproduces the `openai/gpt-5.6-sol` ZDR finding under `--zdr`.
5. Manual: run `anticharon run` twice in the same day against a test data dir; confirm `d1` does not change between the two runs (same-day-rerun fix).
