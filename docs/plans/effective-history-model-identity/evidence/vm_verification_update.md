# VM verification: experimental self-update through MCP (Hermes host)

Manual run on the Hermes VM, 2026-10-07. Starting build `8d17d1b` (0.7.0); `~/.anticharon` backed up first.
Default branch `main` still held 0.6.1, so a reinstall from it is a downgrade by construction.

- The MCP tool `run_update` with `type="install_only"`, called from the Hermes agent, reinstalled Anticharon: `uv tool list` went from `anticharon v0.7.0` to `anticharon v0.6.1`. No `--force` option is involved: `update` never compares versions and the reinstall itself is forced.
- After `/reload-mcp` in the Hermes chat, the reconnected MCP server ran 0.6.1. The agent reported that the version it had been told earlier (0.7.0) was the old process's, i.e. `check_updates` keeps reporting the old version until the server is reloaded. This led to the clearer `RESTART_REQUIRED` message (Hermes: `/reload-mcp`; other hosts: restart or reconnect) and to advertising only `install_only`.
- Not covered by this run: how the 0.6.1 build reads or rewrites the 0.7 store, and the restore to 0.7. The release notes tell users to run `anticharon run --force` after returning to 0.7.0.
