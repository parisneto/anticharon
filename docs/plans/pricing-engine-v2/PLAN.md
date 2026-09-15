# PLAN.md — Pricing Engine v2 (Cache-Aware + Provider-Routable + 28-Day Backfill)

> Long-form plan behind `EXECUTION_CONTRACT.md` (authoritative TL;DR — this document must not contradict it; where something below is not yet settled, it is marked **OPEN** rather than guessed).

## Context

Anticharon's tracked price has always come from OpenRouter's bulk `/api/v1/models` headline `pricing.prompt`/`pricing.completion` fields, fed into a 2-component gross formula (`P_in × w_prompt + P_out × w_completion`). Two independent, evidence-backed defects were found in this:

1. **Cache blindness.** `src/anticharon/log_parser.py` never reads `tokens_cached` from activity logs. Comparing two real exports (`docs/sample/openrouter_activity_2026-08-24.csv`, `docs/sample/openrouter_activity_2026-09-15.csv`) shows 75–82% of prompt tokens served from cache, cutting real cost 59–66%. The gross formula overestimates real cost by 55–75% for cache-heavy agents (see `ADR_CANDIDATE_TOKENS_CACHED.md` Golden Cases #1–#3, #5).
2. **Provider-routability blindness.** The headline price is whichever provider OpenRouter lists, which may not be routable under an account policy (Zero Data Retention being the concrete, verified case). For `openai/gpt-5.6-sol`: listed $2/$10 per 1M, but under ZDR only Azure endpoints are routable at $5–$5.50 in / $30–$33 out (+150–200%). A live-captured `/models/{slug}/endpoints` payload (`sample_gpt56_sol_endpoints.json`, referenced from the private evidence lab, not committed) confirms this via a real `status` field (`-2` = retention-blocked, `0` = routable) and confirms `pricing.input_cache_read`/`input_cache_write` are available per-endpoint from the same public, unauthenticated call — no internal/undocumented endpoint is needed for either of these two data points.

Both defects mean `history.csv`, moving averages, spike/drop alerts, and 30-day analytics have been computed on a price nobody actually pays. Per `EXECUTION_CONTRACT.md`, this is being fixed as one unified initiative — the legacy 2-component formula is **removed**, not kept behind a flag (see Non-Goals discussion below for why "opt-in" was rejected as insufficient).

Additionally, a third, separate concern is pulled into this same initiative per `EXECUTION_CONTRACT.md` §1: **28-day historical backfill** on first tracking a new model, so cold-start doesn't mean 30 days of fabricated flat padding (this was originally ADR 0002's whole scope; it is now one golden case / acceptance-criteria group here, not its own feature).

## Architecture

One new concept, computed per shortlisted model per run: **a `PricePoint` with three named prices**, not one collapsed number:

- **`advertised_price`** — the naive headline value from bulk `/models` (kept for transparency/comparison, per the user's product framing: "show list price, public effective price, and, if a constraint like ZDR is added, the likely inflation/street price").
- **`effective_price`** — cache-aware, 3-component blended price using the account's calibrated `(weight_uncached, weight_cached, weight_completion)` mix against the *cheapest routable-by-default* endpoint's `pricing.prompt/completion/input_cache_read`. This is what actually flows into `history.csv`/MA/alerts/analytics as `current_price_1m` (the canonical tracked price — no more fabricated-cold-start, no more cache-blind number).
- **`policy_price`** (optional, present only when a policy constraint like `zdr_required` is set) — same 3-component formula, restricted to endpoints whose `status >= 0` under that policy's filtered catalog. If zero endpoints qualify, the model is `UNROUTABLE` under that policy (surfaced as a warning; no fabricated price is stored for it that run).

This gives the "supermarket price-tag" comparison the user described without violating the "no multi-column provider matrix" non-goal — it's three named scalars per model per run, not a stored table of every provider.

## Data Model Changes

**`src/anticharon/models.py`:**
- `PromptMixResult` gains `total_cached_tokens`, `total_uncached_tokens`, `weight_uncached_prompt`, `weight_cached_prompt`, `cache_hit_rate` (replacing the current 2-way `weight_prompt`/`weight_completion` as the calibration output — see log_parser below for exact naming reconciliation).
- New `PricePoint` dataclass: `advertised_price: float`, `effective_price: float`, `policy_price: Optional[float]`, `is_policy_routable: Optional[bool]`, `cache_hit_rate_used: float`, with `to_dict()` following the existing rounding convention.
- `ModelPrice` gains `price: PricePoint` (replacing the flat `price_1m` as the source of truth; `price_1m` can remain as a computed property returning `price.effective_price` for the transition, or be removed outright — **OPEN**: see Divergences).
- `PriceRecord.prices: List[Optional[float]]` — slots become nullable (see storage below).
- `PriceWarning` gains a `POLICY_UNROUTABLE` type (message + policy name + which providers were excluded and why).

**`src/anticharon/storage.py` (`history.csv`):**
- Header gains one column: `model,last_updated,current_price_1m,advertised_price_1m,ma_3d,ma_7d,d1..d7,d15,d30` — `current_price_1m` is now the effective price (what MA/alerts/analytics use, unchanged formula consumers downstream); `advertised_price_1m` is new, for the listed-vs-effective comparison view. **This is one new column, not a provider matrix** — flagged as a divergence for approval since the original ADR candidate's non-goal said no schema expansion at all (see Divergences).
- `d1..d7,d15,d30` slots become nullable: write `""` for "no real observation yet" instead of duplicating `current_price_1m`. `read_history`/`write_history` updated to parse `Optional[float]` (empty string → `None`) instead of assuming exactly 9 numeric floats. Old rows (always fully numeric) parse unchanged — no migration script needed, this is a strictly backward-compatible read-path relaxation.

**`src/anticharon/analytics.py` (`calculate_model_analytics`):**
- Currently pads/truncates to exactly 9 elements and treats an all-identical-to-current array as `NEWLY_TRACKED`. Per `EXECUTION_CONTRACT.md` "Historical profiles MUST reflect the evidence actually available... Fewer than 28 days MUST NOT automatically imply NEWLY_TRACKED": rework to compute mean/CV/profile only over the **non-null** slots actually present, with `NEWLY_TRACKED` reserved for "fewer than N real observations exist" (not "fewer than 28 days have elapsed"). Needs an explicit minimum-sample-size constant (**OPEN**: what N — 2? 3? — since CV/stdev are meaningless on a single point; the sample golden case in `EXECUTION_CONTRACT.md` §3 uses a single-observation case expecting `NEWLY_TRACKED`, which sets a lower bound of "1 point → NEWLY_TRACKED", but doesn't say where STABLE/VOLATILE become assignable).

## Module-by-module implementation

**`src/anticharon/log_parser.py`:** read `tokens_cached` per row; compute `Total_Uncached = Total_Prompt - Total_Cached`; emit the 3-way weights and `cache_hit_rate` per the formula in `ADR_CANDIDATE_TOKENS_CACHED.md` §"Mathematical Formulation". `anticharon calibrate` and `config.py`'s stored calibration (`shortlist.json`) gain `weight_uncached_prompt`/`weight_cached_prompt` alongside the existing `weight_completion` (replacing `weight_prompt`).

**`src/anticharon/tracker.py`:** for each shortlisted model, after the existing bulk-catalog lookup (kept, for `advertised_price` + metadata), fetch `GET /api/v1/models/{slug}/endpoints` (new resilient client, mirrors `fetch_openrouter_models`'s timeout+fallback contract exactly), pick the cheapest endpoint (by 3-component blended price) for `effective_price`, and — only when a policy is active — the cheapest `status >= 0` endpoint for `policy_price`. Cold-start: when a model has no prior `history.csv` row, attempt the 28-day backfill (see below) instead of the current `[current_1m] * 9` fabrication; if backfill is unavailable or partial, store only the real points obtained (possibly zero) rather than padding.

**`src/anticharon/discovery.py`:** add `zdr_only: bool = False` to `fetch_catalog()` (appends `?zdr=true`) for reuse by the policy-price filter — no second catalog client.

**`src/anticharon/cli.py` / `mcp.py`:** report all three prices (advertised / effective / policy) wherever a price table is printed or returned, per the user's "supermarket comparison" framing — not just the single collapsed number as today. `check_prices`/`run`/`check` gain a policy toggle (name **OPEN** — `--zdr` was the working name during exploration; may generalize, see Divergences).

## 28-Day Historical Backfill — OPEN, needs a decision before implementation

`EXECUTION_CONTRACT.md` requires backfill from "available public pricing history." The only data source found so far that actually returns a multi-day time series (not just today's snapshot) is OpenRouter's internal, unauthenticated frontend route (`/api/frontend/v1/stats/effective-pricing?...&range=1m`) — this was ADR 0002's original mechanism. The public `/models` and `/models/{slug}/endpoints` endpoints only ever return a current snapshot; there is no publicly documented way to get 28 days of history without either (a) using that internal route, or (b) actually running Anticharon daily for 28 days and accumulating it (which is not "backfill," it's just... time passing).

**This needs your call:** use the internal `effective-pricing` route for backfill (real risk: undocumented, could change shape without notice — same graceful-degradation contract as everything else would apply), or treat "instant 28-day backfill" as not achievable from public data alone and redefine that acceptance criterion to "degrade gracefully with however many real daily observations have accumulated since the model was first shortlisted" (i.e., drop the instant-backfill promise, keep the no-fabrication fix). I have not picked one — implementation of the backfill piece is blocked on this.

## Testing (per `EXECUTION_CONTRACT.md` §2, supersedes `tests/run_tests.py`-only approach)

- Adopt `pytest` (new dependency, amends AGENTS.md Rule 8 for this project). `tests/` restructured: `conftest.py`, `fixtures/` (sanitized real JSON payloads — the `sample_gpt56_sol_endpoints.json` referenced above is a strong starting fixture once copied out of the private evidence lab into `tests/fixtures/`), `test_log_parser.py`, `test_tracker.py`, `test_policy_pricing.py`, `test_golden_pricing.py` (the 5 golden cases from `ADR_CANDIDATE_TOKENS_CACHED.md`, verbatim), `test_analytics.py`.
- Categories, per the contract: unit (formula/boundary), fixture-based parsing, mocked integration (`requests.get` patched via `unittest.mock`/`pytest` fixtures, not the timeout trick), failure-path (timeout/HTTP error/malformed JSON/missing fields — the existing `timeout=0.001` pattern is kept **only** here, scoped honestly), `@pytest.mark.live` (small, excluded from default `uv run pytest`, run explicitly).
- Existing `tests/run_tests.py` / `anticharon test` self-check: keep `anticharon test` (it's a user-facing diagnostic command, not a CI gate) but retire `tests/run_tests.py` as the CI gate in favor of `uv run pytest`. **OPEN**: confirm it's fine to retire the old runner outright vs. keep both running in CI during a transition.

## Docs / spec / changelog / version

- `docs/specs/spec_v1_anticharon.md`: new section documenting the three-price model, the cache-aware formula, the storage schema addition, and the policy-routable filter — supersedes the current single-price Section 3 framing in place (not additive-only, since the legacy formula is being removed per the contract).
- `AGENTS.md`: amend Rule 8 (testing) to reflect pytest adoption; note the `docs/plans/<initiative>/` convention if we keep it (see Divergences).
- `CHANGELOG.md`: `[Unreleased]` entries; this is a MINOR bump (`v0.5.0`) — new capability, and while the pricing *formula* changes, no CLI/MCP interface is removed, only enriched (three prices instead of one), which keeps it MINOR rather than MAJOR under AGENTS.md Rule 11's own definition. **OPEN**: confirm MINOR is right given the persisted `history.csv` values for existing users will retroactively mean something different (not a schema break, but a *semantic* break for anyone diffing historical prices) — this may warrant a CHANGELOG callout even if not a MAJOR version bump.
- `docs/BACKLOG.md`: reconcile with the version already staged in the main checkout (adds "Historical Trajectory Ingestion (ADR 0002)" and "Policy-Aware Super Discovery & ZDR Inflation Engine" as separate items) — under this plan they collapse into one "Pricing Engine v2" backlog entry; propose editing that staged file rather than leaving three overlapping items. **Not yet done — needs your OK since it's your authored file.**

## Explicitly paused / non-goals (carried forward, unchanged)

- No auto-suggest-replacement-model / fallback-search feature (`search_by_tokens` and friends) — paused by explicit instruction, insufficient data/logic maturity.
- No dynamic real-time provider rerouting inside agent sessions.
- No `pricing.overrides` (long-context tiers) or `pricing.discount` modeling this pass — noted as observed in the live payload, parked.
- No OpenRouter dashboard parity.

---

## Divergences from the source documents — need your approval

1. **New `advertised_price_1m` column in `history.csv`.** `ADR_CANDIDATE_TOKENS_CACHED.md`'s original non-goal said no schema expansion at all; I'm proposing one new column (not a provider matrix) to support the three-price comparison view. Alternative: keep `history.csv` single-price and only compute `advertised_price` transiently at query time (not persisted historically) — cheaper, but then "list vs. effective over time" can't be charted later. Your call.
2. **28-day backfill data source is unresolved** (internal `effective-pricing` route vs. redefining the acceptance criterion) — implementation is blocked here until you decide. See section above.
3. **Policy flag naming** (`--zdr` vs. something more general like `--policy zdr`) — `--zdr` is concrete and matches all the evidence gathered so far; a more general flag name is easy to add later if a second policy dimension shows up, so I lean `--zdr` for now, but flagging since the broader "not just ZDR" framing earlier in this conversation might argue for a more generic name from the start.
4. **Retiring `tests/run_tests.py` as the CI gate** in favor of `pytest` — the Execution Contract requires pytest as the mandatory gate but doesn't explicitly say to delete the old runner; I'd retire it rather than maintain two parallel suites, but confirming before deleting anything.
5. **`docs/plans/<initiative>/` as a new documented convention** — this is the first use of this directory shape. If it's meant to be a standing pattern (vs. a one-off for this initiative), AGENTS.md's Rule 4 spec-lifecycle section should document it alongside `docs/specs/pre-work/` and `docs/specs/adr/`. Not done yet — asking first.
6. **`docs/BACKLOG.md` reconciliation** — the main checkout has an uncommitted edit splitting this work into two separate backlog items (historical backfill, ZDR/super-discovery); this plan unifies them into one. I have not edited your staged `BACKLOG.md` — flagging rather than silently changing your file.

## Verification

1. `uv run pytest` (new default gate) — all deterministic tests green, no network access, in a few seconds.
2. `uv run pytest -m live` (explicit, opt-in) — validates the real `/models/{slug}/endpoints` and bulk `/models` contracts still match the fixtures.
3. `uv run anticharon test` — diagnostic self-check still green.
4. Manual: `uv run anticharon check --dry-run --json` shows all three prices for a known cache-heavy model; `uv run anticharon check --zdr --dry-run --json` against `openai/gpt-5.6-sol` reproduces the Figure 2 finding (Azure the only routable endpoint, ~+150–200% vs. advertised).
