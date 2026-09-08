# Pre-Spec: Anticharon Eval Harness & Eval-Driven Development (EDD)

- **Status:** Draft / Work in Progress (Pre-Work)
- **Target Version:** Sprint Next (`v0.4.0` candidate)
- **Related Spec:** `docs/specs/spec_v1_anticharon.md`
- **Related Backlog Item:** `docs/BACKLOG.md` (Priority Backlog)

---

## 1. Executive Summary & Philosophy

Anticharon computes weighted blended pricing, tracking volatility, and serving price discovery over OpenRouter. Historically, pricing systems rely on deterministic unit tests. However, Anticharon interacts with:
1. **Dynamic upstream API catalogs** with constantly moving provider pools, model releases, and alias targets.
2. **Non-deterministic downstream callers**—principally LLM agents such as **Hermes Agent** (and Open Claw orchestrators)—which perform fuzzy reasoning over user-supplied model shortlists.

Relying purely on manual "vibe checks" (inspecting CLI output 3 times) creates fragile agent workflows. Conversely, importing enterprise evaluation frameworks (Promptfoo, LangSmith, Braintrust, DeepEval) violates Anticharon's zero-dependency mandate (Rule 8).

This specification outlines a lightweight, zero-dependency **Eval Harness** built upon **Eval-Driven Development (EDD)**. It serves two distinct actors:
- **Actor A (Internal CI & Test Suite):** Automated boolean pass/fail rule gates and test-fixture validators to verify that candidate shortlists stress all volatility algorithms.
- **Actor B (Host Agents / Hermes via MCP):** MCP tools and prompts that augment the agent on Day 1—enabling a freshman agent to act with 4th-year senior precision when assessing user shortlist health, without rediscovering pricing traps from scratch.

---

## 2. Core Problem: The 3 Variance Patterns

Analysis of real-world OpenRouter shortlists reveals three recurring failure modes that break naive heuristics:

### 2.1 Pattern 1: Cold Start / New Model Blindspots
- **Symptom:** Newly launched models (< 15–30 days old) lack complete 30-day historical time-series data.
- **Risk:** Standard 30-day volatility metrics (`price_spike`, `price_drop`) return default fallback zeros or misleading drift calculations.
- **Impact:** Agents falsely assume the model is "100% price stable" because no variance has accumulated yet.

### 2.2 Pattern 2: Alias Proxies & Moving Targets
- **Symptom:** Slugs such as `anthropic/claude-3-5-sonnet:latest`, `openrouter/auto`, or `:free` are not fixed model weights; they are dynamic aliases that resolve to different backend model endpoints over time.
- **Risk:** Historical price points may reflect distinct model versions under the same slug identifier.
- **Impact:** Cross-period comparisons become invalid, and sudden price changes may reflect an alias repoint rather than provider repricing.

### 2.3 Pattern 3: Provider Liquidity & Spread Skew
- **Symptom:** Some models have a single exclusive host (monopoly provider), while commodity models (e.g. Llama, Mistral) have 15+ competing providers.
- **Risk:** Single-provider models have high counterparty risk and zero price discovery. Multi-provider models feature price spreads exceeding 50% between the cheapest and fastest endpoints.
- **Impact:** An agent unaware of provider depth will fail to optimize routing when a single provider suffers downtime or rate limits.

---

## 3. Dual-Layer Evaluation Architecture

To avoid the limits of both binary pass/fail and complex multi-score dashboards, the eval engine produces a unified output containing **both** a deterministic boolean gate and a rich diagnostic composite payload.

```text
User Shortlist (or Config)
           │
           ▼
┌────────────────────────────────────────┐
│        anticharon eval engine          │
│   (reads cached history or dry-run)   │
└──────────────────┬─────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌──────────────────┐ ┌──────────────────────────────────────┐
│  Layer 1: Gate   │ │       Layer 2: Composite Report      │
│  `is_adequate`   │ │  - confidence_score (0-100)          │
│     (boolean)    │ │  - family_diversity_ratio            │
│                  │ │  - history_maturity_ratio            │
│                  │ │  - alias_volatility_flags            │
│                  │ │  - provider_liquidity_spread         │
│                  │ │  - classification_tag                │
│                  │ │  - structured_recommendations[]      │
└──────────────────┘ └──────────────────────────────────────┘
```

### 3.1 Layer 1: Boolean Rule Gates (`is_adequate`)
Used by automated test runners and CI gates for instant gating:
- `is_adequate = true`: The shortlist contains sufficient historical depth ($\ge 50\%$ mature models), multi-author diversity ($\ge 2$ distinct provider/author namespaces), and no unresolvable single-point failures.
- `is_adequate = false`: The shortlist is severely degraded (e.g. empty, single-model, single-family monopoly, or entirely cold-start).

### 3.2 Layer 2: Diagnostic Composite Metrics
- **`family_diversity_ratio`**: Unique author namespaces divided by total model count.
  - Formula: $\text{count}(\text{distinct}(\text{author\_prefix})) / N$.
  - Example: `openai/chat`, `google/gemini`, `alibaba/qwen` → $3/3 = 1.0$ (High Diversity).
  - Counter-example: `google/gemini-flash`, `google/gemini-pro`, `google/gemini-lite` → $1/3 = 0.33$ (Monoculture Warning).
- **`history_maturity_ratio`**: Proportion of models with $\ge 30$ days of uninterrupted tracking.
- **`alias_risk_count`**: Count of dynamic slugs (`:latest`, `auto`, `:free`).
- **`provider_spread_depth`**: Median provider count across the shortlist. Models with $\ge 3$ providers earn positive liquidity weights.

### 3.3 Classification Archetypes
The engine categorizes shortlists into discrete actionable archetypes:
1. `limited_model_selection`:
   - Single-family author monoculture OR $> 50\%$ models lacking 30-day history.
   - Diagnostic prompt: *"Your shortlist is concentrated in a single provider ecosystem. Adding models to Anticharon does not alter your host agent routing (Anticharon is strictly read-only), but your setup risks single-provider rate limits. Run `model_discovery` to find cross-family alternatives with active price competition."*
2. `rich_model_selection`:
   - $> 3$ models, $> 50\%$ distinct author namespaces, multi-provider backing.
   - Diagnostic prompt: *"Optimal multi-vendor resilience. Anticharon's volatility tracking and price-drop alerts are operating at maximum fidelity."*
3. `volatile_alias_proxy`:
   - Shortlist contains `:latest` or `:free` tags.
   - Diagnostic prompt: *"Dynamic slugs detected. Price drift may reflect upstream backend repointing rather than genuine pricing updates."*
4. `cold_start_monoculture`:
   - Newly launched models dominate the list.
   - Diagnostic prompt: *"Baseline models are <15 days old. 30-day volatility signals are in cold-start mode; rely on real-time blended price rather than historical drift."*

---

## 4. User Stories

### Story 1: The Monoculture Onboarding (Hermes First-Run Experience)
> **Persona:** Alex, an engineer configuring Hermes Agent for code generation.
> **Context:** Alex adds `google/gemini-2.5-flash` as primary and `google/gemini-2.5-pro` as fallback. Both models launched 12 days ago.
> **Interaction:** On startup, Hermes invokes the MCP tool `eval_shortlist()`.
> **Eval Output:** `is_adequate: false`, classification: `limited_model_selection`, diversity: 0.33, maturity: 0.0.
> **Outcome:** Rather than blindly reporting "0.0% price volatility" for 3 weeks, Hermes acts like a senior colleague:
> *"I noticed both your primary and fallback models are from Google's newest lineup (<15 days active). You have zero provider redundancy if Vertex/OpenRouter hits quota limits. I recommend running discovery to pair Gemini with an alternative like `deepseek/deepseek-chat` or `qwen/qwen-2.5-72b-instruct` to capture lower token costs and vendor diversity."*

### Story 2: The Moving Alias Trap
> **Persona:** Bianca, a researcher running nightly evaluation batches.
> **Context:** Bianca specifies `anthropic/claude-3-5-sonnet:latest` and `meta-llama/llama-3.3-70b-instruct:free`.
> **Interaction:** Anticharon CLI run: `uv run anticharon eval`.
> **Eval Output:** `is_adequate: false`, alias warnings triggered on both entries.
> **Outcome:** The terminal displays:
> `[WARN] :latest slug detected for Anthropic Sonnet. Endpoint resolution is volatile.`
> `[WARN] :free tier endpoint detected. Rate limiting and provider dropout probability: HIGH.`
> Bianca pins canonical slug versions before starting long-running benchmark runs.

### Story 3: The CI Stress-Test Gate
> **Persona:** Anticharon maintainer running automated test suites in GitHub Actions.
> **Context:** Maintainer updates test fixtures in `tests/sample/`.
> **Interaction:** `uv run python tests/run_tests.py` executes the eval test gate.
> **Outcome:** If the test shortlist lacks representation from new models, multi-provider models, or alias proxies, the eval assertion fails:
> `AssertionError: Test shortlist fixture fails diversity stress threshold (diversity=0.2 < 0.50). Update tests/sample/shortlist_eval_fixture.json.`

---

## 5. Interface Specifications

### 5.1 CLI Command: `anticharon eval`
```bash
# Evaluate current active shortlist (fast, uses local storage)
uv run anticharon eval

# Force fresh live OpenRouter catalog query & provider spread check
uv run anticharon eval --dry-run

# Strict CI mode (exit code 1 if is_adequate is false)
uv run anticharon eval --strict --format=json
```

**Terminal Output (Human-Friendly Pretty-Print):**
```text
================================================================================
                    ANTICHARON SHORTLIST EVALUATION HARNESS
================================================================================
Models Evaluated: 3 | Providers Sampled: 22 | Catalog Timestamp: 2026-09-08
--------------------------------------------------------------------------------
STATUS: [FAIL] Inadequate Resilience (Score: 42/100)
ARCHETYPE: limited_model_selection

METRICS:
  * Family Diversity:      33.3%  (1 author: google)        [FAIL - Min: 50%]
  * 30-Day Data Maturity:  0.0%   (0/3 models >= 30 days)   [WARN - Cold Start]
  * Alias Stability:       100%   (0 volatile proxies)      [PASS]
  * Provider Liquidity:    1.0 avg (Single provider lock-in) [WARN]

ACTIONABLE RECOMMENDATIONS:
  1. Add at least 1 non-Google model to protect against single-vendor downtime.
  2. Baseline prices are in cold-start mode (<15 days old). Rely on blended
     price rather than 7d/30d volatility deltas.
================================================================================
```

### 5.2 FastMCP Tool: `eval_shortlist`
```python
@mcp.tool()
def eval_shortlist(
    models: list[str] | None = None,
    dry_run: bool = False
) -> dict:
    """Evaluate resilience, historical maturity, and provider variance of a model shortlist.
    
    Args:
        models: Optional list of model slugs. If omitted, evaluates active shortlist.
        dry_run: If True, fetches live OpenRouter catalog. If False, uses cached storage.
        
    Returns:
        Structured evaluation dictionary with boolean gate, score, and recommendations.
    """
```

### 5.3 FastMCP Prompt: `anticharon_eval_advisor`
An Agent-to-Agent (A2A) prompt template loaded into Hermes Agent to govern onboarding analysis:
```text
You are analyzing the user's OpenRouter model routing shortlist using Anticharon.
Given the eval payload below:
{eval_payload}

Follow these directives:
1. State clearly whether the configuration is adequate or limited.
2. If limited_model_selection is flagged, remind the user that Anticharon is strictly
   read-only, and guide them to use `model_discovery` for cost-effective alternatives.
3. If cold_start is flagged, advise caution on relying on historical volatility flags.
```

---

## 6. Test Suite & Golden Fixture Requirements

To maintain Rule 8 (zero heavy dependencies, deterministic <2s execution):
1. **Fixture Dataset:** Create `tests/fixtures/eval_test_matrix.json` containing:
   - Case A: High-diversity enterprise matrix (Anthropic + Google + DeepSeek + Meta).
   - Case B: Single-vendor monoculture (3 Gemini variations).
   - Case C: Alias & Free-tier volatile mix.
   - Case D: Brand-new cold-start model with 0 days of historical data.
2. **Deterministic Assertions:**
   - Verify `is_adequate` evaluates properly across all 4 matrix cases.
   - Verify execution completes in $< 100\text{ms}$ when running against mock storage.

---

## 7. Next Steps & Implementation Roadmap

1. **Review & Approve Pre-Spec:** Validate metric weightings and archetype wording.
2. **Add Golden Fixtures:** Construct `tests/fixtures/eval_test_matrix.json`.
3. **Core Engine:** Implement `src/anticharon/eval.py` (< 200 lines, zero dependencies).
4. **FastMCP Integration:** Expose `eval_shortlist` tool and `anticharon_eval_advisor` prompt in `src/anticharon/mcp.py`.
5. **CLI Subcommand:** Wire `anticharon eval` in `src/anticharon/cli.py`.
