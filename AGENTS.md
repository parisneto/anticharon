# AGENTS.md - Agent Operating Guidelines for Anticharon

Welcome, Agent. This document defines the mandatory operating guidelines, architectural rules, and development standards for any AI agent or contributor developing, modifying, or maintaining the **Anticharon** codebase.

---

## 1. Core Principles & Strict Rules

### Rule 1: Spec-Driven Development Mode (Mandatory Sync)
- All behavior, data models, math formulas, and CLI parameters must be formally documented in [`docs/specs/spec_v1_anticharon.md`](docs/specs/spec_v1_anticharon.md).
- **Strict Rule:** Any change, feature addition, or refactoring in `/src/` MUST be synchronized with `/docs/specs/`. No code changes without updating the spec first or simultaneously.
- If you discover an edge case or change a design decision during implementation, you MUST update the specification file immediately.

### Rule 2: Specification Lifecycle & Staging Pipeline
To maintain a clean public repository while preserving exploratory thought, adhere to the following specification stages:
1. **`docs/specs/pre-work/` (Transient):** Place incoming raw notes, exploratory calculations, and prompt scraps here before formal processing.
2. **`docs/specs/` (Active Source of Truth):** The Agent Architect formalizes pre-work into an authoritative English specification (`spec_vX_*.md`).
3. **`docs/specs/backlog/` (Approved Future Scope):** Store approved design documents for future versions (e.g. `mcp_integration_v2.md`).
4. **`dev_bucket/` (Private Git-Ignored Archive):** Once a pre-work document or draft has been fully incorporated into the official spec, move the raw notes to `dev_bucket/` preserving relative paths.

### Rule 3: Plain Markdown & Unicode Math Notation (No LaTeX)
- **Do NOT use LaTeX, math-mode syntax, or LaTeX-style notation** in Markdown (`$...$`, `$$...$$`, or `$\command$`).
- Use plain Markdown with Unicode symbols that render cleanly across all standard IDEs and GitHub:
  - `→` instead of `$\rightarrow$`
  - `≤` instead of `$\leq$`
  - `≥` instead of `$\geq$`
  - `×` instead of `$\times$`
  - `±` instead of `$\pm$`
  - `≠` instead of `$\neq$`

### Rule 4: Mandatory Changelog Updates
- Every task, bugfix, or feature MUST update [`CHANGELOG.md`](CHANGELOG.md) under the `[Unreleased]` section following the [Keep a Changelog](https://keepachangelog.com/) format.
- Group items clearly under `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, or `### Security`.

### Rule 5: Atomic Git Commits
- Once a functional unit or task is verified, create clean, atomic git commits with semantic commit messages:
  - `feat:` New feature or capability
  - `fix:` Bugfix or calculation correction
  - `docs:` Documentation or specification updates
  - `refactor:` Code restructuring without behavioral change
  - `chore:` Dependency, packaging, or tooling maintenance

### Rule 6: Lightweight, Zero-Dependency Testing
- Do NOT install heavy test frameworks (e.g. pytest, tox, coverage) unless explicitly requested.
- Verification is done via:
  1. Built-in CLI command: `uv run anticharon test`
  2. Standalone zero-dependency test script: `uv run python tests/run_tests.py`
- Tests must execute in < 2 seconds, be deterministic, and avoid making un-mocked live network requests during CI/test runs.

### Rule 7: Strict English Language Policy
- All code, variable names, function names, docstrings, inline comments, specifications, documentation, and commit messages MUST be in English.
- Original draft notes in Portuguese are archived in `dev_bucket/` as historical references; any public documentation must be purely in English.

### Rule 8: Network Safety, Resilient Fallbacks, and Zero Secret Leaks
- Every HTTP request to the OpenRouter API (`https://openrouter.ai/api/v1/models`) must specify a hard timeout (default: 10 seconds).
- If the network call fails or times out, the code must gracefully fallback to the existing `history.csv` without crashing the calling Hermes Agent or cron script.
- Never log, print, or store API keys or private tokens to disk or console output.

---

## 2. Project Architecture & Directory Layout

```text
anticharon/
├── .gitignore                      # Python, venv, data, IDE, and dev_bucket/ ignore rules
├── .python-version                 # Python version pin (3.12)
├── pyproject.toml                  # PEP 621 package metadata & CLI entrypoint
├── README.md                       # Comprehensive user guide, lore, and setup
├── CHANGELOG.md                    # Changelog tracking all versions & unreleased work
├── AGENTS.md                       # This agent guideline file
├── config/
│   └── shortlist.example.json      # Default model shortlist & calibrated weight configuration
├── docs/
│   ├── images/
│   │   └── logo.jpeg               # Official public logo
│   ├── sample/
│   │   └── openrouter_activity_2026-08-24.csv # Test dataset fixture
│   └── specs/
│       ├── spec_v1_anticharon.md   # Authoritative source of truth specification
│       └── backlog/
│           └── mcp_integration_v2.md # Deferred MCP server design
├── src/
│   └── anticharon/
│       ├── __init__.py             # Version and package exports
│       ├── config.py               # Config & environment variable loader
│       ├── models.py               # Dataclasses & types
│       ├── storage.py              # history.csv compact sliding window & cold-start logic
│       ├── tracker.py              # OpenRouter API fetcher, calculations & alerts
│       ├── log_parser.py           # OpenRouter activity CSV parser & prompt mix calculator
│       ├── tester.py               # anticharon test self-check implementation
│       └── cli.py                  # CLI commands (run, check, test, calibrate)
├── tests/
│   └── run_tests.py                # Zero-dependency test suite
└── dev_bucket/                     # [GIT-IGNORED] Private drafts & raw scratch archive
    └── docs/
        ├── TO_add.md
        ├── MCP_operouter_modelprice_optimizer.md
        ├── Image_logos_prompts.md
        ├── images/
        │   ├── logo_alt.jpeg
        │   └── socia_spike.png
        └── specs/
            └── pre-work/
                └── Token Weighting.md
```

---

## 3. Standard Development Workflows

### Setup & Sync (Local Development)
```bash
# Initialize/sync dependencies in virtual environment
uv sync
```

### End-User & Agent Installation
Agents and users can install directly from Git without managing a repo clone:
```bash
uv tool install git+https://github.com/parisneto/anticharon.git
# or
uv pip install git+https://github.com/parisneto/anticharon.git
```

### Self-Test & Validation
```bash
# Run built-in self-check
uv run anticharon test

# Run standalone test runner
uv run python tests/run_tests.py

# Test CLI dry run against OpenRouter live API
uv run anticharon run --dry-run
```

### Calibrating Token Weights from Logs
```bash
# Ingest activity log and automatically update configuration
uv run anticharon calibrate docs/sample/openrouter_activity_2026-08-24.csv
```
