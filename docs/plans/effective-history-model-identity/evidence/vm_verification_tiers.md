# VM verification: service tiers, gate fix, listed basis (EH-8, Track 2, Phase A)

Manual run on the Hermes VM, 2026-10-06 (UTC 23:16). Build: `23b7443`, installed with
`uv tool install --force git+https://github.com/parisneto/anticharon.git@23b7443`; commands:
`anticharon run --force && anticharon check && anticharon history`. Paths sanitized to `~/.anticharon/`.
An earlier run at `1607354` showed luna still at 0.03265 and `endpoint_tags` absent: the live
route carries the tag in `provider_slug`, not `tag` (fixed in `96689f3`).

## Service tiers (AC-8)

- luna 0.03265 → **0.06529** (`azure`, standard); gemini-3.1-flash-lite 0.04081 → **0.08162** (`google-ai-studio`).
- nano 0.04353 (`openai`), qwen 0.01194 (`alibaba`), deepseek-0731 0.01070 (`reka`): unchanged, no tier endpoint was cheapest.
- glm-5.3-flash 0.02917 (`relace`): it has no tier endpoints, so the move from 0.02450 is a list-price change.
- `endpoint_tags` stored for all 6 tracked models: luna 7 (2 tiers: `openai/fast`, `openai/flex`), gemini 8 (4 tiers), deepseek 26 (1 tier), glm 33, nano 3, qwen 1; no unmapped endpoint.
- Alerts persisted at 23:16:05 match the run (default luna; spikes on nano and glm; next fallback deepseek-0731 83.6% cheaper).
- `effective_prices.json` grew from 26 KB to 320 KB because each entry now stores the raw `listed` series (overwritten per refresh, so bounded).

## Side by side (`history`, effective-price analytics vs `listed_basis`)

| Model | Effective (current) | Listed, Anticharon-blended |
|---|---|---|
| deepseek-v4-flash-0731 | VOLATILE, CV 32.2% | VOLATILE, CV 33.1%, 30d −39.2% |
| z-ai/glm-5.3-flash | VOLATILE, CV 22.9% | VOLATILE, CV 23.2%, 30d −1.6% |
| qwen3.7-flash | VOLATILE, CV 12.3% | STABLE, CV 0.0% |
| gpt-5.6-luna | VOLATILE, CV 21.7% | STABLE, CV 0.0% |
| gpt-4.1-nano | SUNSETTING (spike +22.2%) | STABLE, CV 0.0% |
| gemini-3.1-flash-lite | VOLATILE, CV 15.8% | STABLE, CV 0.0% |

Two models (deepseek, glm) agree: their list prices really moved. Four differ because their
list prices were flat and the effective series moved with traffic. nano's SUNSETTING compares
stored observations (nano 0.0924 vs luna 0.0747); on quotes nano (0.04353) is cheaper than luna (0.06529).

## Listed-price history basis (AC-9, D-10), build `c88b278`

Run on the VM at 2026-10-06 23:52 UTC: `anticharon run --force && anticharon check && anticharon history`.

- Cold upgrade from the effective-basis store: the 6 tracked models each have `basis: listed_blend`, 31 observations (2026-09-06 to 2026-10-06), `weights_used` equal to the default calibration, and 32 old observations kept as `legacy_effective_observations`; endpoint tags 7 / 26 / 8 / 3 / 1 / 33. Two entries of models off the shortlist were not touched.
- `run` and `check` show identical prices (luna 0.06529, nano 0.04353, qwen 0.01194, gemini-3.1-flash-lite 0.08162, deepseek-0731 0.01070, glm 0.02279). `alerts.json` at 23:52:45 matches the run (default luna).
- Profiles on the new history: luna, qwen, nano and gemini STABLE (list prices flat); deepseek-0731 VOLATILE (CV 33.1%) with a +20.5% spike against the 7-day average; glm VOLATILE (CV 23.2%). No quote-versus-observation alert, no false SUNSETTING on nano.
- `effective_prices.json` 340,852 bytes (6 models with raw listed steps and the legacy series).
- `shortlist.json` unchanged.
