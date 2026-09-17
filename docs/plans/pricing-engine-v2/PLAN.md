# PLAN.md — Pricing Engine v2 (Cache-Aware + Provider-Routable + 28-Day Backfill)

> Long-form plan behind `EXECUTION_CONTRACT.md` (authoritative TL;DR — this document must not contradict it; where something below is not yet settled, it is marked **OPEN** rather than guessed).
>
> Revision 3 (2026-09-15): all `OPEN` items from revision 2 are now resolved — the JSON store's filename, the analytics minimum-tracking-time threshold, and the `current_price_1m` rename. This plan has no remaining open decisions blocking implementation; the new-session handoff prompt in this conversation should be updated to drop the "ask me about these" paragraph accordingly.

## Context

Anticharon's tracked price has always come from OpenRouter's bulk `/api/v1/models` headline `pricing.prompt`/`pricing.completion` fields, fed into a 2-component gross formula (`P_in × w_prompt + P_out × w_completion`). Two independent, evidence-backed defects were found in this:

1. **Cache blindness.** `src/anticharon/log_parser.py` never reads `tokens_cached` from activity logs. Comparing two real exports (`docs/sample/openrouter_activity_2026-08-24.csv`, `docs/sample/openrouter_activity_2026-09-15.csv`) shows 75–82% of prompt tokens served from cache, cutting real cost 59–66%. The gross formula overestimates real cost by 55–75% for cache-heavy agents (see `ADR_CANDIDATE_TOKENS_CACHED.md` Golden Cases #1–#3, #5).
2. **Provider-routability blindness.** The headline price is whichever provider OpenRouter lists, which may not be routable under an account policy (Zero Data Retention being the concrete, verified case). For `openai/gpt-5.6-sol`: listed $2/$10 per 1M, but under ZDR only Azure endpoints are routable at $5–$5.50 in / $30–$33 out (+150–200%). **Correction (2026-09-16):** the actual real, unauthenticated ZDR signal is `provider_info.dataPolicy.retainsPrompts` from the internal `GET /api/frontend/v1/stats/endpoint` route (see "Policy (ZDR) pricing data source" below) — the public `/models/{slug}/endpoints` call's `status` field was initially assumed to carry this but does not (it reports `0`/routable for everyone on an unauthenticated call). `pricing.input_cache_read`/`input_cache_write` are confirmed available per-endpoint from either route.

Both defects mean `history.csv`, moving averages, spike/drop alerts, and 30-day analytics have been computed on a price nobody actually pays. Per `EXECUTION_CONTRACT.md`, this is being fixed as one unified initiative — the legacy 2-component formula is **removed**, not kept behind a flag.

A third concern is pulled into this same initiative per `EXECUTION_CONTRACT.md` §1: **28-day historical backfill** on first tracking a new model, so cold-start doesn't mean 30 days of fabricated flat padding (this was originally ADR 0002's whole scope; it is now one golden case / acceptance-criteria group here, not its own feature).

## Core pricing semantics (locked 2026-09-15)

This resolves an earlier ambiguity — worth stating precisely since it's foundational:

- **"Blended price" is one concept, always 3-component.** `Price = (P_uncached × w_uncached) + (P_cache_read × w_cached) + (P_out × w_completion)`. There is no second, cache-blind "blended" number anywhere in the system, calibrated or not. Any code path that still does a 2-component blend after this change is a bug.
- **"Advertised" is never blended, and never pinned to whichever endpoint wins.** It's the raw listed reference from the bulk catalog headline, stored as a pair — `advertised_prompt_1m`, `advertised_completion_1m` — regardless of which specific endpoint `effective_price_1m`/`policy_price_1m` end up routing through. Which endpoint OpenRouter actually serves a request from is OpenRouter's routing decision, not Anticharon's — Anticharon only surfaces the shortlist and highlights how routing can impact or benefit real cost; it never decides or reroutes on the agent's/user's behalf (see Non-Goals: no dynamic rerouting). `advertised` exists purely as a transparency/comparison anchor, not as an input to any calculation.
- **`effective_price_1m`** (renamed outright from `current_price_1m` — decided 2026-09-15, for clarity) is the 3-component blend computed against the cheapest endpoint's real pricing. This is a breaking rename of the public-facing field: it changes the JSON key in CLI `--json` output and the `check_prices` MCP tool's return shape, and the `history.csv` column header. **No backward-compatibility shim** — pre-launch, single-digit testers, K.I.S.S.: `read_history()` does not need to accept the old `current_price_1m` header; a stale local `history.csv` from before this change can simply be deleted/regenerated. `CHANGELOG.md` still gets an explicit "breaking: renamed field" callout (cheap to write, no code cost, and it's simply true) so anyone who *does* hit it — including Hermes Agent — knows why.
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

**New granular JSON store (`effective_prices.json`, decided 2026-09-15 — same data directory as `history.csv`, following the same path-resolution hierarchy):**
- Per-model daily time series pulled from OpenRouter's internal `effective-pricing` route.
- Staleness/refresh policy, independent of `history.csv`'s per-run cadence: refresh only when a model's entry is older than 24 hours, not on every `anticharon run` (implemented as `DEFAULT_EFFECTIVE_PRICES_STALE_HOURS` in `storage.py`; this resolves the "Exact cadence OPEN" marker from an earlier revision of this section, which PE2-009 flagged as contradicting revision 3's "no remaining open decisions" claim).
- `history.csv`'s precalculated stats are *derived from* this file, not the other way around — this file is the source of truth for history, `history.csv` is a fast-read cache of summary stats over it.

**Scope correction (PE2-004, resolved 2026-09-17):** this section originally described a *per-model, per-provider* daily time series — one record per provider per day, carrying `date`, `provider`, `effective price` (cache/volume-weighted), `listed price`, `cache hit rate`, and `token share` where available. **That was never implemented, and the decision below formally narrows this section to match what was actually built, rather than leaving the mismatch unresolved or silently rewriting history to pretend it was always the plan.**

What ships instead: `_reduce_to_daily_observations()` (`tracker.py`) collapses all providers' per-endpoint prices for a given day down to the single cheapest blended $/1M for that day before it ever reaches `effective_prices.json` — the stored granularity is `{date, effective_price_1m}` per model per day, not per model per provider per day. Provider identity, per-provider listed price, per-provider cache-hit rate, and token share are computed transiently during that reduction and then discarded; they are not persisted anywhere.

**Why narrowed rather than implemented:** `EXECUTION_CONTRACT.md`'s actual Acceptance Criteria for Storage only requires "the newly required pricing dimensions and the 28-day historical observations needed by downstream calculations" — it does not itself mandate provider-level granularity in the persisted store (that level of detail was this long-form Plan's own elaboration, never promoted into the Contract's criteria). No downstream calculation in this codebase — `history.csv`'s `d1..d30`/`ma_3d`/`ma_7d` derivation, the analytics profiles, the `NEWLY_TRACKED` threshold — consumes per-provider history; all of them only ever need the single cheapest-per-day blended price this design already provides, correctly and with full test coverage (`tests/test_effective_pricing_backfill.py`, `tests/test_storage.py`). Implementing full provider-granular persistence now, with no consumer that needs it, would be exactly the kind of premature/speculative generalization `EXECUTION_CONTRACT.md` §4 Non-Goals rules out ("no generalizing for hypothetical... analytics. Do not solve adjacent discoveries unless required by the defined outcome").
- **Approved reduction rule:** when multiple endpoints report prices for the same calendar day, the stored observation is the *minimum* blended rate among them, and provider identity is intentionally not retained (see `_reduce_to_daily_observations`, tested by `tests/test_effective_pricing_backfill.py::test_reduce_to_daily_observations_picks_cheapest_endpoint_per_day` and locked in explicitly as an approved decision, not an oversight, by `tests/test_effective_pricing_backfill.py::test_reduce_to_daily_observations_provider_identity_is_intentionally_discarded`). This mirrors `effective_price_1m`'s own definition elsewhere in this plan (§"Core pricing semantics": "the 3-component blend computed against the cheapest endpoint's real pricing").
- **Deferred, not abandoned:** provider-level historical granularity (enabling a future "which provider is cheapest over time" view, historical cache-hit-rate trending, or `pricing.overrides`/`pricing.discount` history) is moved to `EXECUTION_CONTRACT.md`'s Deferred section as its own backlog candidate, to be scoped as a real feature against a real downstream consumer if one is ever proposed, rather than built speculatively now.

## 28-Day Backfill — decided: use both sources, cross-validate

On first sync for a model, fetch **both**:
1. The public bulk `/models` catalog (or `/models/{slug}/endpoints`) — gives today's listed price, used for `advertised_prompt_1m`/`advertised_completion_1m`.
2. The internal `effective-pricing` route — gives up to ~30 days of real daily observations, used to populate both the granular JSON store and to precalculate `history.csv`'s `d1..d7,d15,d30`/MA columns.

**Gated cross-validation test (corrected 2026-09-17, PE2-005):** this originally assumed the internal *effective-pricing* route (`/stats/effective-pricing`) itself reports a distinct "listed" baseline to compare against the public catalog. Live-verified 2026-09-17: it does not — its payload only ever contains cache-weighted `effectiveInputPrice`/`effectiveOutputPrice` per provider and aggregate `weightedInputPrice`/`weightedOutputPrice`; there is no raw listed-price field in it at all. The corrected canary instead compares the public catalog's advertised price against the raw per-endpoint listed prices from `/stats/endpoint` (the same route already used for policy/effective pricing elsewhere in this plan) — the bulk catalog's headline is definitionally one of those endpoints' own listed price, so at least one should match it exactly (live-verified: 2 of 7 endpoints matched for `openai/gpt-5.6-luna`). Asserted in `tests/test_effective_pricing_backfill.py::test_effective_pricing_cross_validation_canary` (`@pytest.mark.live`) — if none match, that's the early-warning canary that `/stats/endpoint`'s shape or semantics have drifted from the bulk catalog's.

Graceful degradation: if the internal route fails or its shape has changed, fall back to the same no-fabrication rule as before (store only what the public snapshot gives you — today's single point — rather than fabricating history), exactly like every other network call in this codebase already does.

**Reference implementation to reuse, not reinvent:** a private lab script already implements steps 1-2 above end-to-end (catalog fetch → resolve `canonical_slug`/`permaslug`, including the leading-`~` alias stripping and family-alias registration for cases like `deepseek/deepseek-v4-flash-0423` → `effective-pricing` fetch → tabular rows). Read its logic before writing this fetcher from scratch — it's already been validated against the live API.

## Policy (ZDR) pricing data source — corrected 2026-09-16

Revision 3 assumed ZDR routability would come from the public `/models/{slug}/endpoints` call's `status` field. **That assumption was wrong and is now corrected**, per a real finding from the coding agent's own live re-verification: an unauthenticated call to that endpoint reports `status: 0` (routable) for every provider, including ones that are actually ZDR-blocked — the `-2` status apparently requires an authenticated, ZDR-enabled account to appear, which this project deliberately never assumes a user has (Anticharon has always worked key-free).

**Fix:** use a third internal, unauthenticated frontend route instead — `GET /api/frontend/v1/stats/endpoint?latencyMetric=latency&perfWorkload=text_generation&permaslug={canonical_slug}&variant=standard`. Live-captured and verified 2026-09-15/16 (real payload, not hypothetical). Per endpoint in its `data[]` array:
- `provider_info.dataPolicy.retainsPrompts` (bool) — **the real, unauthenticated ZDR signal.** `false` = ZDR-compliant (e.g. Azure in the captured sample), `true` = not (e.g. direct OpenAI, OpenAI `fast`). This replaces the public `/endpoints` call's `status` field as the policy-routability source entirely for this project.
- Also carries the same pricing shape already relied on (`pricing.prompt`/`completion`/`input_cache_read`/`input_cache_write`/`discount`/`overrides`), plus additional per-provider fields not previously modeled: `provider_info.dataPolicy.training`/`trainingOpenRouter`/`requiresUserIDs`/`headquarters` (useful for future policy dimensions beyond ZDR, not modeled this pass), and live `stats` (p50-p99 latency/throughput, `request_count`) — noted, not consumed this pass (see Non-Goals).
- **Consequence for `tracker.py`/`discovery.py`:** this one route now supersedes the public `/models/{slug}/endpoints` call for the effective-price and policy-price work — it returns a strict superset (same pricing fields, plus the policy data the public route can never provide). Use it as the single per-endpoint data source; the public `/models` bulk catalog is still used separately for `advertised_prompt_1m`/`advertised_completion_1m` (today's headline, unrelated to routing).
- Same graceful-degradation contract as everywhere else: internal/undocumented route, no formal SLA — on failure, fall back to treating the model as policy-unknown (routable-by-default, no fabricated ZDR warning) rather than crashing or guessing.

## Data Model Changes

**`src/anticharon/models.py`:**
- `PromptMixResult` gains `total_cached_tokens`, `total_uncached_tokens`, `weight_uncached_prompt`, `weight_cached_prompt`, `weight_completion`, `cache_hit_rate`.
- New `PricePoint` dataclass: `advertised_prompt_1m: float`, `advertised_completion_1m: float`, `effective_price_1m: float`, `policy_price_1m: Optional[float]`, `is_policy_routable: Optional[bool]`, `cache_hit_rate_used: float`.
- `ModelPrice` gains `price: PricePoint`.
- `PriceRecord.prices: List[Optional[float]]` — nullable slots.
- `PriceWarning` gains `POLICY_UNROUTABLE` (message + policy name + excluded providers + reason).

**`src/anticharon/analytics.py` (`calculate_model_analytics`):**
- Rework to compute mean/CV/profile only over non-null slots actually present; `NEWLY_TRACKED` means "insufficient tracking history," not "fewer than 28 days elapsed." **Threshold decided 2026-09-15:** a model qualifies for `STABLE`/`VOLATILE`/etc. classification once **14 calendar days have elapsed since it was first tracked** (50% of the 28-day window) — measured as elapsed time since `first_seen`, not as a count of non-null slots (those aren't the same thing once backfill can leave gaps, e.g. `d1` and `d15` populated but nothing between). Below 14 days elapsed, always `NEWLY_TRACKED`, matching the single-observation golden case in `EXECUTION_CONTRACT.md`. This constant is intentionally a rough starting guess — configurable, and expected to be revisited with real production data in a future PATCH/MINOR release rather than over-engineered now.

## Module-by-module implementation

- **`log_parser.py`:** read `tokens_cached`; compute uncached/cached/completion weights + cache-hit-rate per the ADR formula.
- **`config.py`:** default config's `weight_prompt`/`weight_completion` decomposed into the 3-way default described above; add the pooled cache-hit-rate constant with a comment citing its provisional/interim status. Also add the `min_tracking_days_for_profile` constant (default `14`, configurable in `shortlist.json` like `spike_threshold_pct` already is) backing the analytics threshold above.
- **`tracker.py`:** fetch bulk catalog (advertised price/metadata) + `/api/frontend/v1/stats/endpoint` (effective/policy price, including real ZDR via `dataPolicy.retainsPrompts` — supersedes the public `/models/{slug}/endpoints` call, see "Policy (ZDR) pricing data source" above) + internal effective-pricing route (backfill, on first sight of a model or per the JSON store's own staleness policy, reusing the reference script's canonical-slug resolution). Apply the same-day-rerun guard.
- **`discovery.py`:** add `zdr_only: bool = False` to `fetch_catalog()`.
- **`cli.py` / `mcp.py`:** surface `advertised` / `effective` / `policy` (when active) as three distinct, clearly-labeled numbers everywhere a price is shown — never collapse them back into one.

## Testing (per `EXECUTION_CONTRACT.md` §2)

- Adopt `pytest`; retire `tests/run_tests.py` outright as the CI gate (confirmed — no transition period). `anticharon test` (the user-facing diagnostic command) is unaffected.
- Structure: `conftest.py`, `fixtures/` (sanitized real JSON payloads — the live-captured `/models/{slug}/endpoints` payload referenced in `ADR_CANDIDATE_TOKENS_CACHED.md` and a live-captured `/api/frontend/v1/stats/endpoint` payload, sanitized to remove any incidental private fields before committing, are both strong starting fixtures), `test_log_parser.py`, `test_tracker.py`, `test_policy_pricing.py` (must include a fixture case where `dataPolicy.retainsPrompts` is `true` for every endpoint — the correct "fully unroutable under ZDR" behavior — since the live sample only showed a mix), `test_golden_pricing.py` (the 5 golden cases, verbatim), `test_analytics.py`, `test_effective_pricing_backfill.py` (includes the cross-validation canary, `@pytest.mark.live`).
- Categories per the contract: unit, fixture-based parsing, mocked integration, failure-path (timeout test stays here only, scoped honestly), `@pytest.mark.live` (excluded from default `uv run pytest`).

## Docs / spec / changelog / version

- `docs/specs/spec_v1_anticharon.md`: new section replacing the current single-price framing with the three-price model + dual storage.
- `AGENTS.md`: amend Rule 8 (pytest adoption) and Rule 4 (add `docs/plans/<initiative>/` as a documented convention — confirmed, see below).
- `CHANGELOG.md`: MINOR bump to `v0.5.0`, with two explicit callouts: (1) **breaking field rename** — `current_price_1m` → `effective_price_1m` in CLI `--json` output and the `check_prices` MCP tool's return shape (existing consumers, including Hermes Agent, must update); (2) historical `history.csv` values now mean something semantically different even where the file format stays readable.
- `docs/BACKLOG.md`: confirmed OK to edit — collapse the two currently-staged separate items (historical backfill, ZDR/super-discovery) into one "Pricing Engine v2" entry pointing at this plan folder.

## Explicitly paused / non-goals (unchanged)

- No auto-suggest-replacement-model / fallback-search feature (`search_by_tokens` and friends) — paused, insufficient data/logic maturity.
- No dynamic real-time provider rerouting inside agent sessions.
- No `pricing.overrides` (long-context tiers) or `pricing.discount` modeling this pass.
- No OpenRouter dashboard parity.

## Deferred / future backlog tasks surfaced by this round

- **Update `DEFAULT_CACHE_HIT_RATE` using the newer TraceLab cache breakdown (found 2026-09-16, not yet applied):** TraceLab's dataset reports Total input 114.2B / Cached-read 109.2B / Append (uncached) input 5.01B / Total output 391.8M. Computed 3-way split: `weight_uncached_prompt ≈ 0.043717`, `weight_cached_prompt ≈ 0.952864`, `weight_completion ≈ 0.003419` (sums to 1.000000). This is a materially different, broader-sourced number than the current interim default (`0.232622`/`0.764478`/`0.0029`, pooled from just the two personal `docs/sample/` exports) — TraceLab shows ~95.3% cache-hit-rate vs. the interim ~76.4%. When this is picked up: update `DEFAULT_CACHE_HIT_RATE`/`DEFAULT_CONFIG` in `config.py`, reconcile the same numbers into `config/shortlist.example.json` (which should already match `config.py` exactly and currently doesn't, off by ~0.00003 — separate small pre-existing inconsistency, fix both at once), and extend the README's existing "Backed by 114 Billion Tokens" TraceLab comparison table with the cache-dimension row.
- Revisit whether `status` values other than `-2`/`0` (e.g. `-5`, observed but unexplained in the live payload) need distinct handling.
- `pricing.overrides` (long-context pricing tiers) and `pricing.discount` — noted, not modeled yet.

---

## Resolved divergences (all nine — six from revision 1, three from revision 2)

1. **`advertised_price_1m` column** — resolved: stored as a raw pair (`advertised_prompt_1m`/`advertised_completion_1m`), never blended. See "Core pricing semantics" above.
2. **28-day backfill data source** — resolved: use both public and internal sources, cross-validated.
3. **Policy flag naming** — proceeding with `--zdr` (no objection raised).
4. **Retiring `tests/run_tests.py`** — resolved: retire outright.
5. **`docs/plans/<initiative>/` convention** — resolved: yes, document in AGENTS.md Rule 4.
6. **`docs/BACKLOG.md` reconciliation** — resolved: approved, collapse to one entry.
7. **Granular JSON store filename/path** — resolved: `effective_prices.json`, same data directory as `history.csv`.
8. **Analytics minimum-sample threshold** — resolved: 14 calendar days elapsed since first tracked (configurable, `min_tracking_days_for_profile`), not a slot-count.
9. **`current_price_1m` rename** — resolved: rename outright to `effective_price_1m`, flagged as a breaking change in `CHANGELOG.md`, with `read_history()` kept backward-compatible for existing local files.

This plan now has **no remaining open decisions**. The next session should implement per this document without needing further sign-off on scope — only genuine new discoveries during implementation should come back as questions.

## Verification

1. `uv run pytest` (default gate) — deterministic, no network, fast.
2. `uv run pytest -m live` — validates real API contracts, including the advertised-vs-endpoint-listed-price cross-validation canary (corrected 2026-09-17, PE2-005 — see "28-Day Backfill" above).
3. `uv run anticharon test` — diagnostic self-check still green.
4. Manual: `uv run anticharon check --dry-run --json` shows advertised/effective (and policy, with `--zdr`) as three distinct numbers for a known cache-heavy model; reproduces the `openai/gpt-5.6-sol` ZDR finding under `--zdr`.
5. Manual: run `anticharon run` twice in the same day against a test data dir; confirm `d1` does not change between the two runs (same-day-rerun fix).
