"""W7 documentation, packaging, and prompt-parity regression coverage."""

import asyncio
from pathlib import Path

from anticharon import __version__, mcp
from anticharon.prompts import PROMPTS

ROOT = Path(__file__).resolve().parents[1]


def test_root_llms_is_the_single_source_and_matches_the_mcp_resource():
    root_llms = ROOT / "llms.txt"

    assert root_llms.exists()
    assert not (ROOT / "src" / "anticharon" / "llms.txt").exists()
    assert mcp.resource_llms_txt() == root_llms.read_text(encoding="utf-8").strip()
    assert f"v{__version__} Beta" in mcp.resource_llms_txt()


def test_llms_lists_every_registered_mcp_surface_and_wheel_mapping():
    llms = (ROOT / "llms.txt").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    tools = asyncio.run(mcp.server.list_tools())
    resources = asyncio.run(mcp.server.list_resources())
    prompts = asyncio.run(mcp.server.list_prompts())

    assert '"llms.txt" = "anticharon/llms.txt"' in pyproject
    for tool in tools:
        assert f"`{tool.name}" in llms
    for resource in resources:
        assert f"`{resource.uri}`" in llms
    for prompt in prompts:
        assert f"`{prompt.name}`" in llms


def test_install_docs_are_beta_and_do_not_advertise_ephemeral_execution():
    docs = [
        ROOT / "README.md",
        ROOT / "llms.txt",
        ROOT / "docs" / "specs" / "spec_v1_anticharon.md",
        ROOT / ".agents" / "skills" / "anticharon" / "SKILL.md",
    ]
    text = "\n".join(path.read_text(encoding="utf-8") for path in docs)

    assert "v0.6.0 Beta" in text
    assert "uv tool install git+https://github.com/parisneto/anticharon.git" in text
    assert "pip install git+https://github.com/parisneto/anticharon.git" in text
    assert "uvx" not in text


def test_prompts_use_mcp_actions_and_guard_remembered_defaults():
    rendered = "\n".join(
        prompt.render(**{
            name: ("test/model" if parameter.annotation is str else 0.5)
            for name, parameter in __import__("inspect").signature(prompt.render).parameters.items()
            if parameter.default is parameter.empty
        })
        for prompt in PROMPTS.values()
    )

    assert "hermes config set" not in rendered
    assert "anticharon model add" not in rendered
    assert "`add_model`" in rendered
    assert "`check_prices`" in rendered
    assert "anticharon://llms.txt" in rendered
