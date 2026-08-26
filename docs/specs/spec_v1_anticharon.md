# Technical Specification: Anticharon (v1)

**Document Version:** 1.0.0  
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
     (GET /api/v1/models)                           (~/.hermes/price_tracker/history.csv)
     * 10s timeout                                  * Compact 1-line-per-model CSV
     * Fallback to local cache                      * 30-day sliding price window
```

---

## 2. Mathematical Specifications & Formulas

### 2.1 Weighted Effective Price per 1 Million Tokens (`Price_1M`)
AI agents typically exhibit heavily skewed usage patterns (e.g., long system prompts, tool output histories, and relatively concise completions). Anticharon uses a weighted blended formula to calculate the true cost per 1M tokens:

```text
Price_1M = ((Prompt_Price_per_Token * Weight_Prompt) + (Completion_Price_per_Token * Weight_Completion)) * 1,000,000
```

* **Default Prompt Weight (`Weight_Prompt`):** `0.9922` (99.22% input)
* **Default Completion Weight (`Weight_Completion`):** `0.0078` (0.78% output)
* **Constraints:** `Weight_Prompt + Weight_Completion = 1.0`

### 2.2 Moving Averages (`MA_3d` and `MA_7d`)
To eliminate daily noise and capture real trends, Anticharon maintains 3-day and 7-day simple moving averages:

```text
MA_3d = (Today_Price + Price_d1 + Price_d2) / 3

MA_7d = (Today_Price + Price_d1 + Price_d2 + Price_d3 + Price_d4 + Price_d5 + Price_d6) / 7
```

Where `Price_dN` represents the recorded weighted price $N$ days ago.

### 2.3 Historical Sliding Window Shift
Historical prices are tracked in a 9-element array corresponding to $[d_1, d_2, d_3, d_4, d_5, d_6, d_7, d_{15}, d_{30}]$.
When a new day's price (`Today_Price`) is recorded:
```text
New_Prices = [Today_Price, Prev_d1, Prev_d2, Prev_d3, Prev_d4, Prev_d5, Prev_d6, Prev_d7, Prev_d15]
```

### 2.4 Cold-Start Handling
When a model is first added to the tracking shortlist and has no prior CSV history:
- The initial price `Today_Price` is replicated across all 9 historical slots ($d_1 \dots d_{30}$).
- `MA_3d` and `MA_7d` are set equal to `Today_Price`.
- This prevents `NaN`, division-by-zero, or false volatility spikes on day 1.

### 2.5 Volatility & Anomaly Detection
Anticharon evaluates percentage variation against the 7-day moving average:

```text
Delta_7d_Pct = ((Current_Price_1M - MA_7d) / MA_7d) * 100
```

#### Warning Trigger Rules:
1. **`PRICE_SPIKE`**: Triggered when `Delta_7d_Pct >= +spike_threshold_pct` (default: `+20.0%`). Indicates that a model's cost increased significantly.
2. **`PRICE_DROP`**: Triggered when `Delta_7d_Pct <= -spike_threshold_pct` (default: `-20.0%`). Indicates a price cut or promotion.
3. **`BEST_OPTION_CHANGED`**: Triggered when the lowest-cost model in the shortlist is different from the currently configured `current_default` model (the first entry in `shortlist.json` or explicit config).

---

## 3. OpenRouter Activity Log Ingestion (`--calculate-prompt-mix`)

To establish exact user-specific prompt/completion weights, Anticharon ingests activity logs exported directly from the OpenRouter dashboard:
- Navigation: OpenRouter $\rightarrow$ Sidebar Logs $\rightarrow$ Change Period (e.g. Past 1 Month) $\rightarrow$ 3 dots menu $\rightarrow$ Export CSV.
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

## 4. Data Storage Schema (`history.csv`)

Storage is optimized to avoid bloated JSON payloads. A single CSV file maintains exactly **one line per model**:

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

## 5. Configuration Schema (`shortlist.json`)

```json
{
  "shortlist": [
    "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-v4-flash-0423",
    "qwen/qwen3.7-flash",
    "openai/gpt-5.6-luna",
    "google/gemini-3.1-flash-lite",
    "minimax/minimax-m2.7",
    "google/gemini-2.5-flash-lite"
  ],
  "weight_prompt": 0.9922,
  "weight_completion": 0.0078,
  "spike_threshold_pct": 20.0
}
```

### Path Resolution Hierarchy:
1. **CLI Arguments:** `--config <path>` and `--data-dir <path>` (highest priority).
2. **Environment Variables:** `ANTICHARON_CONFIG` and `ANTICHARON_DATA_DIR`.
3. **Local Workspace Mode (Running inside repo):**
   - Config: `./config/shortlist.json` (or `./config/shortlist.example.json`)
   - Data: `./data/history.csv`
4. **Standalone / Tool Mode (When installed via `uv tool install` or run as an MCP server):**
   - Config: `~/.anticharon/shortlist.json`
   - Data: `~/.anticharon/history.csv`

---

## 6. CLI Command Interface

### Primary Commands:
```bash
# 1. Standard execution: Fetch API, update history.csv, print human-readable summary & warnings
anticharon run

# 2. Dry run / Check: Fetch API, calculate prices without modifying history.csv
anticharon check --dry-run

# 3. Output as JSON for scripting & agent piping
anticharon run --json

# 4. Self-test: Validate environment, connectivity, config, math, and write permissions
anticharon test

# 5. Ingest OpenRouter log export CSV and calculate agent prompt/completion mix
anticharon calculate-prompt-mix path/to/openrouter_activity.csv [--update-config]
```

---

## 7. Safety, Resilience & Network Fallback

1. **Timeout Control:** Every OpenRouter HTTP request has an explicit `10.0` second timeout.
2. **Fallback Mode:** If the OpenRouter API fails (HTTP error, connection reset, timeout), Anticharon reads `history.csv`, logs a non-fatal warning, and returns the last known prices with `fallback: true` status.
3. **No Unhandled Crashes:** Agents relying on Anticharon via cron or automated pipelines receive valid structured data even during network disruptions.
