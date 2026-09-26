# ADR 0001: Unified Single-Repository Architecture & Stdio Isolation for MCP and CLI

## Status
Accepted

## Date
2026-09-03

## Context
Anticharon started as an ultra-lightweight CLI tool and analytical price intelligence engine for OpenRouter models. As autonomous LLM agents (specifically **Hermes Agent** and **Claude Desktop**) emerged as primary orchestrators, the project required a standard **Model Context Protocol (MCP)** interface over `stdio`.

We evaluated two architectural strategies:
1. **Fork / Separate Repositories:** Creating a separate `anticharon-mcp` package/repository exclusively for the MCP server, importing or vendoring core logic.
2. **Unified Hybrid Repository:** Maintaining a single codebase where core calculation logic is decoupled from presentation, exposing both CLI subcommands (`anticharon run`, `check`, `history`) and an MCP server subcommand (`anticharon mcp`).

Additionally, MCP over `stdio` requires strict transport isolation: `stdout` must be reserved strictly for JSON-RPC 2.0 frames (`{"jsonrpc": "2.0", ...}`). Any unsolicited text (e.g. human ASCII charts, colored banners, debug prints) written to `stdout` will corrupt the JSON-RPC framing and cause the MCP client to drop the connection.

## Decision

### 1. Unified Single-Repository (Hybrid Model)
We decided to keep Anticharon as a single, unified repository.
- **Rationale:** The mathematical models (prompt/completion weighted pricing), 30-day sliding history arrays, analytical profile classification, catalog discovery, and Hermes configuration synchronization are 100% identical between CLI and MCP. Forking would duplicate business logic, create release sync latency, and complicate end-user installation.
- **Industry Precedent:** Top-tier developer tools (e.g., `ast-grep`, `sqlite-mcp`, `fetch-mcp`, `docker-mcp`) successfully adopt this hybrid architecture, offering both CLI and MCP subcommands from a single wheel.

### 2. Strict Stdio Separation
- **Presentation Decoupling:** Core logic modules (`src/anticharon/tracker.py`, `analytics.py`, `discovery.py`, `models.py`, `storage.py`, `hermes.py`) return pure typed Python dataclasses or dictionaries without emitting print statements to `stdout`.
- **CLI Adapter (`src/anticharon/cli.py`):** Formats dataclasses into human-readable terminal TUI tables, colorized banners, and ASCII sparklines.
- **MCP Adapter (`src/anticharon/mcp.py`):** Wraps core functions in FastMCP tool/resource handlers, delegating JSON serialization to the MCP framework.
- **Log Routing:** During `anticharon mcp` execution, all logging, non-fatal fallback warnings, and diagnostic telemetry are redirected to `sys.stderr`, which MCP hosts safely log without affecting JSON-RPC message framing.

### 3. User Configuration & Storage Hierarchy (XDG Compliance)
To support both local workstation execution and containerized agent environments, Anticharon follows a standardized configuration resolution hierarchy:
- **Priority 1:** Explicit CLI flags (`--config`, `--data-dir`)
- **Priority 2:** Environment variables (`ANTICHARON_CONFIG`, `ANTICHARON_DATA_DIR`)
- **Priority 3:** Local repository files (`./config/shortlist.json`, `./data/history.csv`) when running from source
- **Priority 4:** Standard XDG user configuration (`$XDG_CONFIG_HOME/anticharon/shortlist.json` or `~/.config/anticharon/shortlist.json`)
- **Priority 5:** User home fallback (`~/.anticharon/shortlist.json` and `~/.anticharon/history.csv`)

### 4. Self-Describing Agent-to-Agent (A2A) Schemas & `_hints`
LLM tool callers operate on semantic interpretations of JSON keys. In agentic pipelines like Hermes, a boolean key named `fallback: true` or `api_offline_fallback: true` can be misconstrued as referring to Hermes's own model failover list (`fallback_providers`).
- **Standard:** Every MCP tool response dictionary includes:
  - `data_source`: `"live_api"` or `"cached_history"`
  - `api_offline_fallback`: Explicit boolean declaring HTTP cache fallback
  - `_hints`: In-band dictionary defining key semantics directly in the payload
  - MCP Resource `anticharon://llms.txt`: Machine-readable operational briefing

## Consequences
- **Positive:**
  - Zero code duplication; single source of truth for pricing math, moving averages, and catalog discovery.
  - Persistent deployment: install from Git with `uv tool install` or `pip install`, then configure the installed `anticharon mcp` command in the MCP host.
  - Stdio safety guarantees zero connection drops.
  - Full compliance with both human CLI and autonomous agent orchestration needs.
- **Negative / Trade-offs:**
  - Runtime dependency on `mcp>=1.3.0` added to `pyproject.toml`.
