# Anticharon

Use this skill when installing or configuring Anticharon for a user.

Install persistently with one supported mode:

```bash
uv tool install git+https://github.com/parisneto/anticharon.git
```

```bash
pip install git+https://github.com/parisneto/anticharon.git
```

Configure the host using the MCP examples in [README.md](../../../README.md).
For a source checkout, contributors can use `uv run --directory
$HOME/src/anticharon anticharon mcp`.

In MCP mode, read `anticharon://llms.txt` before selecting tools or relying on
a remembered model default. Use `check_updates` to inspect an installed
version; `run_update` is experimental and requires explicit user intent.
