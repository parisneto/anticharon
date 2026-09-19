"""Hermes Agent configuration detection, stream-grep extraction, and shortlist synchronization."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from anticharon.config import get_config_path, load_config, update_config_shortlist


def resolve_hermes_config_path(
    custom_path: str | Path | None = None,
    prompt_if_missing: bool = False
) -> Path | None:
    """Resolve the path to Hermes configuration file (config.yaml).
    
    Resolution Priority:
    1. Explicit custom_path (--hermes-config)
    2. Environment variable HERMES_CONFIG (path to config.yaml)
    3. Environment directory $HERMES_HOME/config.yaml
    4. Standard user home ~/.hermes/config.yaml
    5. Interactive prompt (only when prompt_if_missing is True and stdin is a TTY)
    """
    if custom_path:
        p = Path(custom_path).expanduser()
        return p if p.exists() else None

    if "HERMES_CONFIG" in os.environ:
        p = Path(os.environ["HERMES_CONFIG"]).expanduser()
        if p.exists():
            return p

    if "HERMES_HOME" in os.environ:
        p = Path(os.environ["HERMES_HOME"]).expanduser() / "config.yaml"
        if p.exists():
            return p

    home_path = Path.home() / ".hermes" / "config.yaml"
    if home_path.exists():
        return home_path

    if prompt_if_missing and sys.stdin.isatty():
        try:
            val = input("\n⚠️ Hermes config not found at ~/.hermes/config.yaml.\nEnter path to config.yaml (or press Enter to skip): ").strip()
            if val:
                p = Path(val).expanduser()
                if p.exists():
                    return p
                else:
                    print(f"File not found: {p}", file=sys.stderr)
        except (EOFError, KeyboardInterrupt):
            pass

    return None


def fetch_models_from_cli() -> dict[str, Any] | None:
    """Tier 1: Query Hermes active models directly via `hermes config get`."""
    if not shutil.which("hermes"):
        return None

    try:
        # 1. Query model block
        proc_model = subprocess.run(
            ["hermes", "config", "get", "model"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if proc_model.returncode != 0 or not proc_model.stdout.strip():
            return None

        default_model = None
        for line in proc_model.stdout.splitlines():
            line_s = line.strip()
            if line_s.startswith("default:"):
                default_model = line_s.split("default:", 1)[1].strip().strip("'\"")
                break

        if not default_model:
            return None

        # 2. Query fallback_providers
        fallback_models: list[str] = []
        proc_fallback = subprocess.run(
            ["hermes", "config", "get", "fallback_providers"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if proc_fallback.returncode == 0 and proc_fallback.stdout.strip():
            raw_val = proc_fallback.stdout.strip()
            if raw_val.startswith("'") and raw_val.endswith("'"):
                raw_val = raw_val[1:-1]
            elif raw_val.startswith('"') and raw_val.endswith('"'):
                raw_val = raw_val[1:-1]

            try:
                data = json.loads(raw_val)
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            prov = item.get("provider", "").lower()
                            mod = item.get("model", "").strip()
                            if prov == "openrouter" and mod:
                                fallback_models.append(mod)
            except Exception:
                # Regex fallback if JSON parse fails
                matches = re.findall(
                    r'\{[^{}]*"provider"\s*:\s*"openrouter"[^{}]*"model"\s*:\s*"([^"]+)"[^{}]*\}',
                    raw_val
                )
                if matches:
                    fallback_models = matches

        all_models = [default_model] + [m for m in fallback_models if m != default_model]
        return {
            "source": "cli:hermes",
            "method": "cli",
            "default_model": default_model,
            "fallback_models": fallback_models,
            "all_models": all_models
        }
    except Exception:
        return None


def extract_models_from_file(config_file: Path) -> dict[str, Any] | None:
    """Tier 2: Stream-grep Hermes config file line-by-line without loading entire file."""
    if not config_file.exists():
        return None

    default_model: str | None = None
    default_provider: str | None = None
    fallback_models: list[str] = []

    in_model_block = False
    in_fallback_block = False
    current_fallback_provider: str | None = None
    current_fallback_model: str | None = None

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.rstrip("\r\n")
                indent = len(line_str) - len(line_str.lstrip(" "))
                stripped = line_str.strip()

                if not stripped or stripped.startswith("#"):
                    continue

                # Model section tracking (top-level only)
                if indent == 0 and (stripped == "model:" or stripped.startswith("model:")):
                    in_model_block = True
                    in_fallback_block = False
                    continue

                # Fallback providers tracking (top-level only)
                if indent == 0 and stripped.startswith("fallback_providers:"):
                    in_model_block = False
                    val = stripped.split("fallback_providers:", 1)[1].strip()
                    if val:
                        # Inline JSON or list string
                        if (val.startswith("'") and val.endswith("'")) or (val.startswith('"') and val.endswith('"')):
                            val = val[1:-1]
                        try:
                            data = json.loads(val)
                            if isinstance(data, list):
                                for item in data:
                                    if isinstance(item, dict):
                                        prov = item.get("provider", "").lower()
                                        mod = item.get("model", "").strip()
                                        if prov == "openrouter" and mod:
                                            fallback_models.append(mod)
                        except Exception:
                            matches = re.findall(
                                r'\{[^{}]*"provider"\s*:\s*"openrouter"[^{}]*"model"\s*:\s*"([^"]+)"[^{}]*\}',
                                val
                            )
                            if matches:
                                fallback_models.extend(matches)
                        
                        # If both default_model and fallback_models are resolved, early exit
                        if default_model and fallback_models:
                            break
                    else:
                        in_fallback_block = True
                        continue

                if in_model_block:
                    if indent == 0:
                        in_model_block = False
                    else:
                        if stripped.startswith("default:"):
                            default_model = stripped.split("default:", 1)[1].strip().strip("'\"")
                        elif stripped.startswith("provider:"):
                            default_provider = stripped.split("provider:", 1)[1].strip().strip("'\"")

                elif in_fallback_block:
                    if indent == 0:
                        in_fallback_block = False
                    else:
                        # Indented YAML list items
                        if stripped.startswith("- "):
                            if current_fallback_provider == "openrouter" and current_fallback_model:
                                fallback_models.append(current_fallback_model)
                            current_fallback_provider = None
                            current_fallback_model = None
                            sub = stripped[2:].strip()
                            if sub.startswith("provider:"):
                                current_fallback_provider = sub.split("provider:", 1)[1].strip().strip("'\"").lower()
                            elif sub.startswith("model:"):
                                current_fallback_model = sub.split("model:", 1)[1].strip().strip("'\"")
                        elif stripped.startswith("provider:"):
                            current_fallback_provider = stripped.split("provider:", 1)[1].strip().strip("'\"").lower()
                        elif stripped.startswith("model:"):
                            current_fallback_model = stripped.split("model:", 1)[1].strip().strip("'\"")

            # Finalize any trailing YAML item
            if in_fallback_block and current_fallback_provider == "openrouter" and current_fallback_model:
                fallback_models.append(current_fallback_model)

        if not default_model:
            return None

        all_models = [default_model] + [m for m in fallback_models if m != default_model]
        return {
            "source": str(config_file),
            "method": "file_grep",
            "default_model": default_model,
            "fallback_models": fallback_models,
            "all_models": all_models
        }
    except Exception:
        return None


def get_hermes_models(
    custom_path: str | Path | None = None,
    prompt_if_missing: bool = False,
    use_cli: bool = True
) -> dict[str, Any] | None:
    """Retrieve Hermes active models using Tier 1 (CLI) or Tier 2 (File Stream Grep)."""
    # If custom path explicitly specified, use file extractor directly
    if custom_path:
        p = Path(custom_path).expanduser()
        return extract_models_from_file(p)

    # Tier 1: Try Hermes CLI first if enabled
    if use_cli:
        cli_result = fetch_models_from_cli()
        if cli_result:
            return cli_result

    # Tier 2: Stream-grep configuration file
    cfg_path = resolve_hermes_config_path(custom_path=None, prompt_if_missing=prompt_if_missing)
    if cfg_path:
        return extract_models_from_file(cfg_path)

    return None


def sync_hermes_to_config(
    hermes_models: dict[str, Any],
    config_path: Path | None = None,
    dry_run: bool = False
) -> tuple[bool, list[str], Path]:
    """Synchronize Hermes models into Anticharon shortlist.json.
    
    Returns (changed: bool, shortlist: List[str], config_path: Path).
    """
    target_path = config_path or get_config_path()
    current_cfg = load_config(target_path)
    current_shortlist = current_cfg.get("shortlist", [])

    new_models = hermes_models.get("all_models", [])
    if not new_models:
        return False, current_shortlist, target_path

    changed = (current_shortlist != new_models)

    if changed and not dry_run:
        saved_path = update_config_shortlist(new_models, target_path)
        return True, new_models, saved_path

    return changed, new_models, target_path
