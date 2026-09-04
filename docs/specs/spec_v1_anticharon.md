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

### 3.1 Weighted Effective Price per 1 Million Tokens (`Price_1M`)
```text
Price_1M = ((Prompt_Price_per_Token × Weight_Prompt) + (Completion_Price_per_Token × Weight_Completion)) × 1,000,000
```

* **Calibrated Default Prompt Weight (`Weight_Prompt`):** `0.9971` (99.71% input)
* **Calibrated Default Completion Weight (`Weight_Completion`):** `0.0029` (0.29% output)
* **Constraint:** `Weight_Prompt + Weight_Completion = 1.0`

### 3.2 Moving Averages (`MA_3d` and `MA_7d`)
```text
MA_3d = (Today_Price + Price_d1 + Price_d2) / 3

MA_7d = (Today_Price + Price_d1 + Price_d2 + Price_d3 + Price_d4 + Price_d5 + Price_d6) / 7
```

Where `Price_dN` represents the recorded weighted price N days ago.

### 3.3 Historical Sliding Window Shift
Historical prices are tracked in a 9-element array corresponding to `[d1, d2, d3, d4, d5, d6, d7, d15, d30]`.
When a new day's price (`Today_Price`) is recorded:
```text
New_Prices = [Today_Price, Prev_d1, Prev_d2, Prev_d3, Prev_d4, Prev_d5, Prev_d6, Prev_d7, Prev_d15]
```

### 3.4 Cold-Start Handling
When a model is first added to the tracking shortlist and has no prior CSV history:
- The initial price `Today_Price` is replicated across all 9 historical slots (`d1` through `d30`).
- `MA_3d` and `MA_7d` are set equal to `Today_Price`.
- This prevents `NaN`, division-by-zero, or false volatility spikes on day 1.

### 3.5 Volatility & Anomaly Detection
Anticharon evaluates percentage variation against the 7-day moving average:

```text
Delta_7d_Pct = ((Current_Price_1M - MA_7d) / MA_7d) × 100
```

#### Warning Trigger Rules:
1. **`PRICE_SPIKE`**: Triggered when `Delta_7d_Pct ≥ +spike_threshold_pct` (default: `+20.0%`). Indicates a price hike.
2. **`PRICE_DROP`**: Triggered when `Delta_7d_Pct ≤ -spike_threshold_pct` (default: `-20.0%`). Indicates a discount or promotion.
3. **`BEST_OPTION_CHANGED`**: Triggered when the lowest-cost model in the shortlist is different from the configured `current_default` model (the first entry in `shortlist.json`).

---

## 4. OpenRouter Activity Log Calibration (`anticharon calibrate`)

To update operational weights whenever a fresh CSV is exported from the OpenRouter dashboard:
- Navigation: OpenRouter → Sidebar Logs → Select Period (e.g. Past 1 Month) → 3 dots menu → Export CSV.
- Columns processed: `tokens_prompt`, `tokens_completion`.

### Computation Formula:
```text
Total_Prompt_Tokens = sum(tokens_prompt)
Total_Completion_Tokens = sum(tokens_completion)
Total_Tokens = Total_Prompt_Tokens + Total_Completion_Tokens

Weight_Prompt = Total_Prompt_Tokens / Total_Tokens
Weight_Completion = Total_Completion_Tokens / Total_Tokens
```

---

## 5. Data Storage Schema (`history.csv`)

Storage maintains exactly **one line per model**:

### Header Format:
```csv
model,last_updated,current_price_1m,ma_3d,ma_7d,d1,d2,d3,d4,d5,d6,d7,d15,d30
```

### Column Definitions:
| Column | Type | Description |
| :--- | :--- | :--- |
| `model` | string | OpenRouter model ID / slug (e.g. `openai/gpt-5.6-luna`) |
| `last_updated` | ISO-8601 string | UTC timestamp of last update |
| `current_price_1m` | float | Latest weighted blended price per 1M tokens |
| `ma_3d` | float | 3-day simple moving average |
| `ma_7d` | float | 7-day simple moving average |
| `d1` to `d7` | float | Prices from 1 to 7 days ago |
| `d15` | float | Price recorded 15 days ago |
| `d30` | float | Price recorded 30 days ago |

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
  "weight_prompt": 0.9971,
  "weight_completion": 0.0029,
  "spike_threshold_pct": 20.0
}
```

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
- Newly discovered models are automatically initialized in `history.csv` using the cold-start replication rule (Section 3.4).
- User-configured weights (`weight_prompt`, `weight_completion`, `spike_threshold_pct`) are preserved during synchronization.
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
   - Condition: All historical price slots are identical due to day 1 cold-start padding.
   - Meaning: Insufficient trend history. Observational baseline establishing.

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
- **Description:** Fetches current OpenRouter model pricing for the monitored shortlist, calculates weighted blended cost per 1M tokens, computes 7-day moving averages, evaluates volatility alerts (PRICE_SPIKE, PRICE_DROP, BEST_OPTION_CHANGED), and attaches 30-day analytical intelligence profiles.
- **Parameters:**
  - `force_refresh` (boolean, optional, default: `false`): Force fresh HTTP fetch from OpenRouter API, ignoring local cache.
  - `dry_run` (boolean, optional, default: `true`): Calculate prices without updating `history.csv` sliding window.
  - `include_analytics` (boolean, optional, default: `true`): Attach 30-day statistical profiles, badges, and sibling alternatives.
- **Return Payload:** Self-describing JSON dictionary containing `timestamp`, `data_source` (`live_api` or `cached_history`), `api_offline_fallback` (boolean), `prices_shortlist`, `priceWarnings`, `hermes_integration`, and in-band `_hints`.

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
- `anticharon://history.csv`: Raw 30-day sliding history table (`model,last_updated,current_price_1m,ma_3d,ma_7d,d1..d7,d15,d30`).
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




