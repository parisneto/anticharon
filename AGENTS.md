# AGENTS.md - Agent Operating Guidelines for Anticharon

Welcome, Agent. This document defines the mandatory operating guidelines, architectural rules, and development standards for any AI agent or contributor developing, modifying, or maintaining the **Anticharon** codebase.

---

## 1. Core Principles & Strict Rules

### Rule 1: Spec-Driven Development Mode (Mandatory Sync)
- All behavior, data models, math formulas, and CLI parameters must be formally documented in [`docs/specs/spec_v1_anticharon.md`](docs/specs/spec_v1_anticharon.md).
- **Strict Rule:** Any change, feature addition, or refactoring in `/src/` MUST be synchronized with `/docs/specs/`. No code changes without updating the spec first or simultaneously.
- If you discover an edge case or change a design decision during implementation, you MUST update the specification file immediately.

### Rule 2: Mandatory Changelog Updates
- Every task, bugfix, or feature MUST update [`CHANGELOG.md`](CHANGELOG.md) under the `[Unreleased]` section following the [Keep a Changelog](https://keepachangelog.com/) format.
- Group items clearly under `### Added`, `### Changed`, `### Deprecated`, `### Removed`, `### Fixed`, or `### Security`.

### Rule 3: Atomic Git Commits
- Once a functional unit or task is verified, create clean, atomic git commits with semantic commit messages:
  - `feat:` New feature or capability
  - `fix:` Bugfix or calculation correction
  - `docs:` Documentation or specification updates
  - `refactor:` Code restructuring without behavioral change
  - `chore:` Dependency, packaging, or tooling maintenance

### Rule 4: Lightweight, Zero-Dependency Testing
- Do NOT install heavy test frameworks (e.g. pytest, tox, coverage) unless explicitly requested.
- Verification is done via:
  1. Built-in CLI command: `uv run anticharon test`
  2. Standalone zero-dependency test script: `uv run python tests/run_tests.py`
- Tests must execute in < 2 seconds, be deterministic, and avoid making un-mocked live network requests during CI/test runs.

### Rule 5: Strict English Language Policy
- All code, variable names, function names, docstrings, inline comments, specifications, documentation, and commit messages MUST be in English.
- Original draft notes in Portuguese located in `docs/` are historical references only; any new documentation must be purely in English.

### Rule 6: Network Safety, Resilient Fallbacks, and Zero Secret Leaks
- Every HTTP request to the OpenRouter API (`https://openrouter.ai/api/v1/models`) must specify a hard timeout (default: 10 seconds).
- If the network call fails or times out, the code must gracefully fallback to the existing `history.csv` without crashing the calling Hermes Agent or cron script.
- Never log, print, or store API keys or private tokens to disk or console output.

---

## 2. Project Architecture & Directory Layout

```text
anticharon/
├── .gitignore                      # Python, venv, data, IDE, and OS ignore rules
├── .python-version                 # Python version pin (3.12)
├── pyproject.toml                  # PEP 621 package metadata & CLI entrypoint
├── README.md                       # Comprehensive user guide, lore, and setup
├── CHANGELOG.md                    # Changelog tracking all versions & unreleased work
├── AGENTS.md                       # This agent guideline file
├── config/
│   └── shortlist.example.json      # Default model shortlist & weight configuration
├── docs/
│   ├── sample/                     # Real-world sample logs (e.g., OpenRouter activity CSV)
│   ├── specs/
│   │   └── spec_v1_anticharon.md   # Source of truth specification
│   └── mcp_integration_guide.md    # Future MCP integration blueprint (Backlog)
├── src/
│   └── anticharon/
│       ├── __init__.py             # Version and package exports
│       ├── config.py               # Config & environment variable loader
│       ├── models.py               # Dataclasses & types
│       ├── storage.py              # history.csv compact sliding window & cold-start logic
│       ├── tracker.py              # OpenRouter API fetcher, calculations & alerts
│       ├── log_parser.py           # OpenRouter activity CSV parser & prompt mix calculator
│       ├── tester.py               # anticharon test self-check implementation
│       └── cli.py                  # CLI commands & argument parsing
└── tests/
    └── run_tests.py                # Zero-dependency test suite
```

---

## 3. Standard Development Workflows

### Setup & Sync (Local Development)
```bash
# Initialize/sync dependencies in virtual environment
uv sync
# Or install in editable mode
uv pip install -e .
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

### Calculating Prompt/Completion Ratio from Logs
```bash
uv run anticharon calculate-prompt-mix docs/sample/openrouter_activity_2026-08-24.csv --update-config
```
