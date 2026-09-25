"""Model shortlist management: add, remove, and list shortlisted models."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anticharon.config import (
    get_config_path,
    get_history_path,
    load_config,
    update_config_shortlist,
)
from anticharon.hermes import get_hermes_models, shortlist_write_message
from anticharon.models import AgentMessage
from anticharon.storage import get_effective_prices_path, read_effective_prices
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
    entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Payload only; callers wrap it with `build_envelope(payload, self.messages, started)`."""
        return {
            "status": self.status,
            "action": self.action,
            **({"model": self.model} if self.model else {}),
            "dry_run": self.dry_run,
            "shortlist": self.shortlist,
            "models": self.entries,
            **({"config_path": self.config_path} if self.config_path else {})
        }


def add_model(
    model_id: str,
    dry_run: bool = False,
    config_path: Path | None = None,
    default: bool = False,
) -> ManagementResult:
    """Add a model to shortlist.json after exact live catalog validation."""
    cfg_file = config_path or get_config_path()
    hermes_info = get_hermes_models(prompt_if_missing=False)
    cfg = load_config(cfg_file, legacy_source="hermes" if hermes_info else "manual")
    shortlist = cfg.get("shortlist", [])
    entries = cfg.get("_shortlist_entries", [])

    model_clean = model_id.strip()

    # Check if already present
    if model_clean in shortlist:
        if default:
            hermes_info = get_hermes_models(prompt_if_missing=False)
            if hermes_info and hermes_info.get("default_model"):
                return ManagementResult("refused", "add", model_clean, dry_run, shortlist, str(cfg_file),
                    [AgentMessage("error", "SOURCE_MANAGED", "Hermes owns the default model; set the default in Hermes configuration.", model=model_clean)])
            updated_entries = []
            for item in entries:
                entry = dict(item)
                if entry.get("source") == "manual" and entry.get("order") == 0:
                    entry.pop("order")
                updated_entries.append(entry)
            for entry in updated_entries:
                if entry["model"] == model_clean:
                    entry["order"] = 0
            if not dry_run:
                update_config_shortlist(shortlist, cfg_file, entries=updated_entries)
            return ManagementResult("success", "add", model_clean, dry_run, shortlist, str(cfg_file),
                [shortlist_write_message(True, dry_run, f"setting '{model_clean}' as default")], updated_entries)
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
            entries=entries,
        )

    messages: list[AgentMessage] = []
    catalog = fetch_openrouter_models(timeout=5.0)
    if not catalog:
        return ManagementResult("error", "add", model_clean, dry_run, shortlist, str(cfg_file),
            [AgentMessage("error", "CATALOG_UNAVAILABLE", "OpenRouter's model catalog is unavailable; retry later.", model=model_clean)])
    if model_clean not in catalog:
        return ManagementResult("refused", "add", model_clean, dry_run, shortlist, str(cfg_file),
            [AgentMessage("error", "NO_EXACT_MATCH", f"No exact catalog match for '{model_clean}'; it was not added.",
                action={"mcp": f"discover_models(query=\"{model_clean}\")", "cli": f"anticharon model discover \"{model_clean}\""}, model=model_clean)])

    if default and hermes_info and hermes_info.get("default_model"):
        return ManagementResult("refused", "add", model_clean, dry_run, shortlist, str(cfg_file),
            [AgentMessage("error", "SOURCE_MANAGED", "Hermes owns the default model; set the default in Hermes configuration.", model=model_clean)])

    new_shortlist = shortlist + [model_clean]
    new_entries = [dict(entry) for entry in entries]
    if default:
        for entry in new_entries:
            if entry.get("source") == "manual" and entry.get("order") == 0:
                entry.pop("order")
    new_entries.append({"model": model_clean, "source": "manual", **({"order": 0} if default else {})})
    saved_path = cfg_file if dry_run else update_config_shortlist(new_shortlist, cfg_file, entries=new_entries)
    messages.append(shortlist_write_message(True, dry_run, f"adding '{model_clean}'"))
    return ManagementResult(
        status="success",
        action="add",
        model=model_clean,
        dry_run=dry_run,
        shortlist=new_shortlist,
        entries=new_entries,
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
    hermes_info = get_hermes_models(prompt_if_missing=False)
    cfg = load_config(cfg_file, legacy_source="hermes" if hermes_info else "manual")
    shortlist = cfg.get("shortlist", [])
    entries = cfg.get("_shortlist_entries", [])

    model_clean = model_id.strip()

    if model_clean not in shortlist:
        return ManagementResult(
            status="error",
            action="remove",
            model=model_clean,
            dry_run=dry_run,
            shortlist=shortlist,
            entries=entries,
            config_path=str(cfg_file),
            messages=[AgentMessage(
                "error", "SHORTLIST_UNCHANGED",
                f"Model '{model_clean}' is not in the shortlist; nothing was removed.",
                action={"mcp": "read resource anticharon://shortlist.json", "cli": "anticharon model list"},
                model=model_clean,
            )],
        )

    entry = next((item for item in entries if item["model"] == model_clean), {"source": "manual"})
    if entry.get("source") != "manual":
        return ManagementResult("refused", "remove", model_clean, dry_run, shortlist, str(cfg_file),
            [AgentMessage("error", "SOURCE_MANAGED", f"'{model_clean}' is managed by {entry['source']}; remove it from that source.", model=model_clean)])

    new_shortlist = [m for m in shortlist if m != model_clean]
    new_entries = [item for item in entries if item["model"] != model_clean]
    saved_path = cfg_file if dry_run else update_config_shortlist(new_shortlist, cfg_file, entries=new_entries)
    return ManagementResult(
        status="success",
        action="remove",
        model=model_clean,
        dry_run=dry_run,
        shortlist=new_shortlist,
        entries=new_entries,
        config_path=str(saved_path),
        messages=[shortlist_write_message(True, dry_run, f"removing '{model_clean}'")],
    )


def list_models(config_path: Path | None = None) -> ManagementResult:
    """List all currently shortlisted models."""
    cfg_file = config_path or get_config_path()
    hermes_info = get_hermes_models(prompt_if_missing=False)
    cfg = load_config(cfg_file, legacy_source="hermes" if hermes_info else "manual")
    shortlist = cfg.get("shortlist", [])
    effective_path = get_effective_prices_path(get_history_path().parent)
    stored = read_effective_prices(effective_path)
    entries = [
        {**entry, "is_default": entry.get("order") == 0, **({"canonical_slug": stored[entry["model"]]["canonical_slug"]}
                     if stored.get(entry["model"], {}).get("canonical_slug") else {})}
        for entry in cfg.get("_shortlist_entries", [])
    ]

    return ManagementResult(
        status="success",
        action="list",
        dry_run=False,
        shortlist=shortlist,
        entries=entries,
        config_path=str(cfg_file)
    )
