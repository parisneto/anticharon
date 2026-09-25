"""Model shortlist management: add, remove, and list shortlisted models."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anticharon.config import get_config_path, load_config, update_config_shortlist
from anticharon.hermes import shortlist_write_message
from anticharon.models import AgentMessage
from anticharon.tracker import fetch_openrouter_models


@dataclass
class ManagementResult:
    """Result of model addition, removal, or listing."""
    status: str
    action: str
    model: str | None = None
    dry_run: bool = False
    shortlist: list[str] = field(default_factory=list)
    config_path: str | None = None
    messages: list[AgentMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Payload only; callers wrap it with `build_envelope(payload, self.messages, started)`."""
        return {
            "status": self.status,
            "action": self.action,
            **({"model": self.model} if self.model else {}),
            "dry_run": self.dry_run,
            "shortlist": self.shortlist,
            **({"config_path": self.config_path} if self.config_path else {})
        }


def add_model(
    model_id: str,
    dry_run: bool = False,
    config_path: Path | None = None,
    validate_catalog: bool = True
) -> ManagementResult:
    """Add a model to shortlist.json after optional catalog validation."""
    cfg_file = config_path or get_config_path()
    cfg = load_config(cfg_file)
    shortlist = cfg.get("shortlist", [])

    model_clean = model_id.strip()

    # Check if already present
    if model_clean in shortlist:
        return ManagementResult(
            status="warning",
            action="add",
            model=model_clean,
            dry_run=dry_run,
            shortlist=shortlist,
            config_path=str(cfg_file),
            messages=[AgentMessage(
                "warning", "SHORTLIST_UNCHANGED",
                f"Model '{model_clean}' is already in the shortlist; nothing was added.",
                model=model_clean,
            )],
        )

    # Optional validation against OpenRouter live catalog
    messages: list[AgentMessage] = []
    if validate_catalog:
        catalog = fetch_openrouter_models(timeout=5.0)
        if catalog and model_clean not in catalog:
            matching = next((k for k in catalog if k.startswith(model_clean)), None)
            note = (
                f"closest catalog alias is '{matching}'" if matching
                else "the slug was not found in OpenRouter's live catalog"
            )
            messages.append(AgentMessage(
                "warning", "NO_EXACT_MATCH",
                f"No exact catalog match for '{model_clean}' ({note}); it was still added as typed.",
                action={"mcp": f"discover_models(query=\"{model_clean}\")", "cli": f"anticharon model discover \"{model_clean}\""},
                model=model_clean,
            ))

    new_shortlist = shortlist + [model_clean]
    saved_path = cfg_file if dry_run else update_config_shortlist(new_shortlist, cfg_file)
    messages.append(shortlist_write_message(True, dry_run, f"adding '{model_clean}'"))
    return ManagementResult(
        status="success",
        action="add",
        model=model_clean,
        dry_run=dry_run,
        shortlist=new_shortlist,
        config_path=str(saved_path),
        messages=messages,
    )


def remove_model(
    model_id: str,
    dry_run: bool = False,
    config_path: Path | None = None
) -> ManagementResult:
    """Remove a model from shortlist.json."""
    cfg_file = config_path or get_config_path()
    cfg = load_config(cfg_file)
    shortlist = cfg.get("shortlist", [])

    model_clean = model_id.strip()

    if model_clean not in shortlist:
        return ManagementResult(
            status="error",
            action="remove",
            model=model_clean,
            dry_run=dry_run,
            shortlist=shortlist,
            config_path=str(cfg_file),
            messages=[AgentMessage(
                "error", "SHORTLIST_UNCHANGED",
                f"Model '{model_clean}' is not in the shortlist; nothing was removed.",
                action={"mcp": "read resource anticharon://shortlist.json", "cli": "anticharon model list"},
                model=model_clean,
            )],
        )

    new_shortlist = [m for m in shortlist if m != model_clean]
    saved_path = cfg_file if dry_run else update_config_shortlist(new_shortlist, cfg_file)
    return ManagementResult(
        status="success",
        action="remove",
        model=model_clean,
        dry_run=dry_run,
        shortlist=new_shortlist,
        config_path=str(saved_path),
        messages=[shortlist_write_message(True, dry_run, f"removing '{model_clean}'")],
    )


def list_models(config_path: Path | None = None) -> ManagementResult:
    """List all currently shortlisted models."""
    cfg_file = config_path or get_config_path()
    cfg = load_config(cfg_file)
    shortlist = cfg.get("shortlist", [])

    return ManagementResult(
        status="success",
        action="list",
        dry_run=False,
        shortlist=shortlist,
        config_path=str(cfg_file)
    )
