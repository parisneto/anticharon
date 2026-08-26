# Anticharon 🪙⚖️

<p align="center">
  <img src="docs/images/logo.jpeg" alt="Anticharon Logo" width="480" />
</p>

> **The ferryman who minimizes the fare instead of demanding toll.**
> An ultra-lightweight, resilient OpenRouter API price tracker, volatility detector, and token cost optimizer for **Hermes Agent** and automated LLM workflows.

---

## 📖 The Mythos

In Greek mythology, **Charon** is the grim ferryman who demands an obol coin toll to carry souls across the rivers Styx and Acheron. In modern agentic AI systems, every prompt expansion, reasoning chain, and tool history represents an accumulating token toll.

**Anticharon** is the counter-agent: the vigilant watcher that monitors OpenRouter model pricing, computes weighted prompt/completion blended costs, detects unexpected price spikes or promotional drops, and ensures your agents always cross the token river for the lowest possible toll.

---

## ✨ Key Features

- **Blended Weighted Pricing:** Calculates realistic cost per 1M tokens based on your agent's actual prompt vs completion ratio (calibrated default: **99.71% input / 0.29% output**).
- **Empirically Corroborated:** The default Input/Output token weights are backed by real-world coding agent traces from [UW TraceLab's "How Do AI Agents Use LLMs?" paper](https://tracelab.cs.washington.edu/llms/) (coding agent traces on Claude Code & Codex recording 99.63% in / 0.37% out across 69.3B tokens), almost identical to the author's 99.71% / 0.29% operational ratio far from it's 1st billion tokens (and I have no rush to get there).
- **Reduces AI Slop & Cost Anxiety:** Accurate blended pricing eliminates token anxiety, empowering developers and agents to run more or less discounted premium AI frontier models responsibly (meaning : on a dev personal budget).
- **TUI ASCII Price Spectrum Chart:** Instant visual ASCII bar chart in every run showing relative pricing distribution from `▲ Cheaper` to `▼ More Expensive`, badging `🏆 [BEST]` and `★ [DEFAULT]`.
- **Model Discovery Engine (`anticharon model discover`):** Search and filter OpenRouter's entire catalog (~417+ models) with multi-criteria keywords, output modalities (`--modality text`), promotional / free discounts (`--promo`), and price threshold expressions (`--filter "price < 10"`).
- **Model Shortlist Management (`anticharon model add / remove / list`):** Manage your configuration right from the terminal with live catalog slug validation and `--dry-run` safety.
- **One-Command Calibration (`anticharon calibrate`):** Directly ingest CSV log exports from OpenRouter to automatically calculate and save your exact prompt/completion mix for better life quality. Remember: Y.M.M.V. (Your Mix May Vary).
- **Moving Average & Volatility Detection:** Tracks 3-day and 7-day moving averages (`MA_3d`, `MA_7d`) to trigger instant `PRICE_SPIKE`, `PRICE_DROP`, and `BEST_OPTION_CHANGED` alerts. No Scientific Analysis here just simple moving averages and threshold based logic.
- **Compact Historical Storage:** Keeps a clean, 1-line-per-model sliding CSV history (`history.csv`) with automatic cold-start padding.
- **Resilient & Safe:** 10-second API timeouts with graceful fallback to local cache when offline or rate-limited.
- **Built-in Self-Test (`anticharon test`):** Instant pre-flight checks validating runtime environment, dependencies, math calculations, and network access.
- **Fast, Zero-Bloat Distribution:** Managed with `uv`, runnable as a standalone CLI or directly installed from Git.

---

## 🚀 Installation & Distribution

### 1. For Agents & End Users (Direct from Git)
Install and run `anticharon` directly without manually cloning the repository:

```bash
# Using uv tool (recommended)
uv tool install git+https://github.com/parisneto/anticharon.git

# Or via uv pip in an active environment
uv pip install git+https://github.com/parisneto/anticharon.git
```

### 2. For Contributors & Local Development
```bash
git clone https://github.com/parisneto/anticharon.git
cd anticharon

# Initialize virtual environment and dependencies
uv sync
```

---

## 💻 CLI Usage

### Run Price Tracking
```bash
# Standard run: fetches OpenRouter, updates history, prints report & ASCII price chart
uv run anticharon run

# Dry-run / Check: calculates prices without saving to disk
uv run anticharon check --dry-run

# Output structured JSON (ideal for Hermes or script piping)
uv run anticharon run --json
```

### Model Discovery & Catalog Exploration
```bash
# Search models by family / name
uv run anticharon model discover "gemini"

# Discover promotional and free (:free, $0.00) models
uv run anticharon model discover --promo

# Multi-criteria filtering (provider, modality, price threshold expressions)
uv run anticharon model discover "qwen" --modality text --max-price 0.50
uv run anticharon model discover --promo --filter "openai" --filter "anthropic"
uv run anticharon model discover --filter "gemini" --filter "price < 0.20"
```

### Manage Shortlisted Models
```bash
# List current shortlist
uv run anticharon model list

# Add a model with live catalog validation (or preview with --dry-run)
uv run anticharon model add "google/gemini-3.7-flash"
uv run anticharon model add "google/gemini-3.7-flash" --dry-run

# Remove a model from shortlist
uv run anticharon model remove "minimax/minimax-m2.7"
```

### Run Environment & Network Self-Test
```bash
uv run anticharon test
```

### Calibrate Token Weights from OpenRouter Activity Logs
1. Go to OpenRouter: **Sidebar Logs** (`https://openrouter.ai/logs`)
2. Select your timeframe on the top right (e.g. **Past 1 Month**)
3. Click the **3 dots menu** → **Export** to download the CSV file.
4. Run Anticharon:
```bash
# Ingest log and automatically update your shortlist.json config
uv run anticharon calibrate path/to/openrouter_activity.csv

# Or inspect the calculated ratio without modifying configuration
uv run anticharon calibrate path/to/openrouter_activity.csv --dry-run
```

---

## ⚙️ Configuration (`shortlist.json`)

Anticharon looks for configuration in:
1. Environment variable `ANTICHARON_CONFIG` (if set)
2. `~/.hermes/price_tracker/shortlist.json`
3. Local `./config/shortlist.json` (fallback)

### Example `shortlist.json`:
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

---

## 🤖 Hermes Agent & Cron Integration

Run Anticharon daily via cron to alert Hermes or generate reports:

```bash
# Run daily at 08:00 UTC and save JSON output
0 8 * * * anticharon run --json > ~/.hermes/price_tracker/latest_prices.json
```

---

## 📄 License
MIT License. Created by Paris Piedade Neto.
feel free to reach me on [LinkedIn](https://www.linkedin.com/in/parisneto/)

## 💬 Feedback

Feel free to open an issue or submit a pull request. Any feedback or suggestions are welcome!
