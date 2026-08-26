"""Model shortlist management: add, remove, and list shortlisted models."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from anticharon.config import load_config, get_config_path, update_config_shortlist
from anticharon.tracker import fetch_openrouter_models


@dataclass
class ManagementResult:
    """Result of model addition, removal, or listing."""
    status: str
    action: str
    model: Optional[str] = None
    dry_run: bool = False
    message: str = ""
    shortlist: List[str] = None
    config_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            **({"model": self.model} if self.model else {}),
            "dry_run": self.dry_run,
            "message": self.message,
            "shortlist": self.shortlist or [],
            **({"config_path": self.config_path} if self.config_path else {})
        }


def add_model(
    model_id: str,
    dry_run: bool = False,
    config_path: Optional[Path] = None,
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
            message=f"Model '{model_clean}' is already in the shortlist.",
            shortlist=shortlist,
            config_path=str(cfg_file)
        )

    # Optional validation against OpenRouter live catalog
    catalog_warning = ""
    if validate_catalog:
        catalog = fetch_openrouter_models(timeout=5.0)
        if catalog and model_clean not in catalog:
            matching = next((k for k in catalog if k.startswith(model_clean)), None)
            if matching:
                catalog_warning = f" (Note: Found closest catalog alias '{matching}')"
            else:
                catalog_warning = " (Note: Model slug was not found in OpenRouter's live catalog)"

    new_shortlist = shortlist + [model_clean]

    if not dry_run:
        saved_path = update_config_shortlist(new_shortlist, cfg_file)
        return ManagementResult(
            status="success",
            action="add",
            model=model_clean,
            dry_run=False,
            message=f"Successfully added '{model_clean}' to shortlist.{catalog_warning}",
            shortlist=new_shortlist,
            config_path=str(saved_path)
        )
    else:
        return ManagementResult(
            status="success",
            action="add",
            model=model_clean,
            dry_run=True,
            message=f"[DRY RUN] Would add '{model_clean}' to shortlist.{catalog_warning}",
            shortlist=new_shortlist,
            config_path=str(cfg_file)
        )


def remove_model(
    model_id: str,
    dry_run: bool = False,
    config_path: Optional[Path] = None
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
            message=f"Model '{model_clean}' is not in the shortlist.",
            shortlist=shortlist,
            config_path=str(cfg_file)
        )

    new_shortlist = [m for m in shortlist if m != model_clean]

    if not dry_run:
        saved_path = update_config_shortlist(new_shortlist, cfg_file)
        return ManagementResult(
            status="success",
            action="remove",
            model=model_clean,
            dry_run=False,
            message=f"Successfully removed '{model_clean}' from shortlist.",
            shortlist=new_shortlist,
            config_path=str(saved_path)
        )
    else:
        return ManagementResult(
            status="success",
            action="remove",
            model=model_clean,
            dry_run=True,
            message=f"[DRY RUN] Would remove '{model_clean}' from shortlist.",
            shortlist=new_shortlist,
            config_path=str(cfg_file)
        )


def list_models(config_path: Optional[Path] = None) -> ManagementResult:
    """List all currently shortlisted models."""
    cfg_file = config_path or get_config_path()
    cfg = load_config(cfg_file)
    shortlist = cfg.get("shortlist", [])

    return ManagementResult(
        status="success",
        action="list",
        dry_run=False,
        message=f"Found {len(shortlist)} shortlisted models.",
        shortlist=shortlist,
        config_path=str(cfg_file)
    )
