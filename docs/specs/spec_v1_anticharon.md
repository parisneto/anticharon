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
- **University of Washington TraceLab Evidence:** Real-world coding agent traces collected from Claude Code and Codex ([TraceLab](https://tracelab.cs.washington.edu/)) recorded **69.1 billion input tokens** against **256.7 million output tokens**, working out to **99.63% input / 0.37% output**.
- **Author Operational Dataset (August 2026):** Ingestion of 159 agent generations (`openrouter_activity_2026-08-24.csv`) totaling **17,437,925 tokens** yielded **17,386,716 prompt tokens (99.71%)** vs **51,209 completion tokens (0.29%)**.
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

## 7. CLI Command Interface

### Primary Commands & Options:
```bash
# 1. Standard execution: Fetch API, update ./data/history.csv, print report & alerts
anticharon run

# 2. Dry run / Check: Fetch API, calculate prices without modifying history.csv
anticharon check --dry-run

# 3. Suppress Hermes auto-detection and run purely standalone
anticharon run --no-hermes
anticharon check --no-hermes

# 4. Explicit Hermes config path
anticharon run --hermes-config /custom/path/to/config.yaml

# 5. Output structured JSON (ideal for Hermes or script piping)
anticharon run --json

# 6. Custom paths and timeouts
anticharon run --config ./my_config.json --data-dir ./my_data --timeout 15.0

# 7. Pre-flight self-test: Validate runtime, config, math, permissions, network, and Hermes integration
anticharon test

# 8. Calibrate weights from OpenRouter activity log and update shortlist.json
anticharon calibrate path/to/openrouter_activity.csv

# 9. Calculate and display token mix without modifying configuration (dry-run)
anticharon calibrate path/to/openrouter_activity.csv --dry-run

# 10. Explicitly sync models from Hermes config
anticharon model sync [--hermes-config PATH] [--dry-run]

# 11. Model Management (Add / Remove / List)
anticharon model add "google/gemini-3.7-flash" [--dry-run]
anticharon model remove "minimax/minimax-m2.7" [--dry-run]
anticharon model list [--json]

# 12. Model Discovery & Exploration
anticharon model discover "gemini"
anticharon model discover --promo
anticharon model discover "qwen" --modality text --max-price 0.50
anticharon model discover --filter "openai" --filter "price < 10"
```

---

## 8. Safety, Resilience & Network Fallback

1. **Timeout Control:** Every OpenRouter HTTP request has an explicit `10.0` second timeout.
2. **Fallback Mode:** If the OpenRouter API fails (HTTP error, connection reset, timeout), Anticharon reads `history.csv`, logs a non-fatal warning, and returns the last known prices with `fallback: true` status.
3. **No Unhandled Crashes:** Agents relying on Anticharon via cron or automated pipelines receive valid structured data even during network disruptions.

