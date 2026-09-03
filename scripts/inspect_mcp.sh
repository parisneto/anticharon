#!/usr/bin/env bash
# ==============================================================================
# Launch MCP Inspector for Anticharon Development & Testing
# ==============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "🪙 Starting MCP Inspector for Anticharon..."
echo "📂 Repository: ${REPO_DIR}"

if command -v npx >/dev/null 2>&1; then
  npx @modelcontextprotocol/inspector uv --directory "${REPO_DIR}" run anticharon mcp
else
  echo "Error: npx not found. Please install Node.js / npm to use MCP Inspector." >&2
  exit 1
fi
