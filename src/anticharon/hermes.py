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

# Detection outcomes for a single source (CLI tier / file tier), per Issue #4:
#   "complete"    -- parseable default model AND the complete fallback set.
#   "incomplete"  -- a model configuration demonstrably exists, but the complete
#                    set cannot be established (e.g. non-empty fallback_providers
#                    output that parses to zero entries).
#   "unavailable" -- the source cannot be read/queried at all; represented by a
#                    `None` return from the tier function (no dict to carry a flag).
DETECTION_COMPLETE = "complete"
DETECTION_INCOMPLETE = "incomplete"

INCOMPLETE_DETECTION_WARNING = (
    "Hermes model detection is incomplete: its fallback model list could not be fully "
    "read. The existing Anticharon shortlist was preserved unchanged (no overwrite)."
)

# Literal scalars Hermes may emit for an unset fallback_providers key. These are
# a definite "no fallbacks configured" answer, not an unreadable one.
_EMPTY_FALLBACK_SCALARS = {"", "null", "none", "~", "[]", "{}", "nil"}


def _parse_fallback_value(raw_val: str) -> tuple[list[str], bool]:
    """Parse a `fallback_providers` value into OpenRouter model slugs.

    Accepts the inline JSON list form and the raw YAML list form the Hermes CLI
    actually emits (`- provider: openrouter\\n  model: <slug>`).

    Returns `(models, recognized)`. `recognized` is False only when the value is
    non-empty yet no known structure could be read from it -- an `incomplete`
    detection, never a silently-empty success (Issue #4).
    """
    raw_val = raw_val.strip()
    if len(raw_val) >= 2 and raw_val[0] == raw_val[-1] and raw_val[0] in "'\"":
        raw_val = raw_val[1:-1].strip()

    if raw_val.lower() in _EMPTY_FALLBACK_SCALARS:
        return [], True

    # 1. Inline JSON list (json.JSONDecodeError subclasses ValueError)
    try:
        data = json.loads(raw_val)
    except (ValueError, TypeError):
        data = None
    if isinstance(data, list):
        models = []
        for item in data:
            if isinstance(item, dict):
                prov = str(item.get("provider", "")).lower()
                mod = str(item.get("model", "")).strip()
                if prov == "openrouter" and mod:
                    models.append(mod)
        return models, True

    # 2. Regex salvage for malformed/truncated JSON object syntax
    matches = re.findall(
        r'\{[^{}]*"provider"\s*:\s*"openrouter"[^{}]*"model"\s*:\s*"([^"]+)"[^{}]*\}',
        raw_val
    )
    if matches:
        return matches, True

    # 3. Raw YAML list (the format the Hermes CLI emits -- Issue #4 root cause)
    models = []
    entries = 0
    provider: str | None = None
    model: str | None = None
    for line in raw_val.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") or stripped == "-":
            if provider == "openrouter" and model:
                models.append(model)
            provider = None
            model = None
            entries += 1
            stripped = stripped[1:].strip()
        if stripped.startswith("provider:"):
            provider = stripped.split("provider:", 1)[1].strip().strip("'\"").lower()
        elif stripped.startswith("model:"):
            model = stripped.split("model:", 1)[1].strip().strip("'\"")
    if provider == "openrouter" and model:
        models.append(model)

    return models, entries > 0


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
        detection = DETECTION_COMPLETE
        proc_fallback = subprocess.run(
            ["hermes", "config", "get", "fallback_providers"],
            capture_output=True,
            text=True,
            timeout=2.0
        )
        if proc_fallback.returncode == 0 and proc_fallback.stdout.strip():
            fallback_models, recognized = _parse_fallback_value(proc_fallback.stdout)
            if not recognized:
                # Non-empty but unreadable output: a model configuration exists,
                # but the complete set cannot be established (Issue #4).
                detection = DETECTION_INCOMPLETE

        all_models = [default_model] + [m for m in fallback_models if m != default_model]
        return {
            "source": "cli:hermes",
            "method": "cli",
            "detection": detection,
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
    detection = DETECTION_COMPLETE

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

                # Any top-level key closes an open fallback block -- flush the
                # pending item first, exactly as the EOF path below does.
                # Without this the final entry is silently dropped whenever the
                # block is followed by another section instead of EOF (Issue #4).
                if indent == 0 and in_fallback_block:
                    if current_fallback_provider == "openrouter" and current_fallback_model:
                        fallback_models.append(current_fallback_model)
                    current_fallback_provider = None
                    current_fallback_model = None
                    in_fallback_block = False

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
                        inline_models, recognized = _parse_fallback_value(val)
                        fallback_models.extend(inline_models)
                        if not recognized:
                            detection = DETECTION_INCOMPLETE

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
            "detection": detection,
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
    """Retrieve Hermes active models using Tier 1 (CLI) or Tier 2 (File Stream Grep).

    Source order is never reversed: the CLI is preferred when it returns a
    `complete` result. If the CLI result is `incomplete` (a configuration exists
    but its full model set could not be read) or `unavailable` (`None`), the file
    tier is tried. A `complete` file result is authoritative and fully clears the
    incomplete CLI state. If neither tier reaches `complete`, the incomplete
    result is returned as-is so callers can warn and protect the shortlist (#4).
    """
    # If custom path explicitly specified, use file extractor directly
    if custom_path:
        p = Path(custom_path).expanduser()
        return extract_models_from_file(p)

    # Tier 1: Try Hermes CLI first if enabled
    cli_result = fetch_models_from_cli() if use_cli else None
    if cli_result and cli_result.get("detection") == DETECTION_COMPLETE:
        return cli_result

    # Tier 2: Stream-grep configuration file
    cfg_path = resolve_hermes_config_path(custom_path=None, prompt_if_missing=prompt_if_missing)
    file_result = extract_models_from_file(cfg_path) if cfg_path else None
    if file_result and file_result.get("detection") == DETECTION_COMPLETE:
        return file_result

    return cli_result or file_result


def sync_hermes_to_config(
    hermes_models: dict[str, Any],
    config_path: Path | None = None,
    dry_run: bool = False
) -> tuple[bool, list[str], Path]:
    """Synchronize Hermes models into Anticharon shortlist.json.

    A `complete` detection is authoritative and may legitimately shrink the
    shortlist. An `incomplete` one must never overwrite a longer existing
    shortlist with a shorter/default-only list derived from it (Issue #4).

    Returns (changed: bool, shortlist: List[str], config_path: Path).
    """
    target_path = config_path or get_config_path()
    current_cfg = load_config(target_path)
    current_shortlist = current_cfg.get("shortlist", [])

    new_models = hermes_models.get("all_models", [])
    if not new_models:
        return False, current_shortlist, target_path

    incomplete = hermes_models.get("detection", DETECTION_COMPLETE) != DETECTION_COMPLETE
    if incomplete and len(new_models) < len(current_shortlist):
        return False, current_shortlist, target_path

    changed = (current_shortlist != new_models)

    if changed and not dry_run:
        saved_path = update_config_shortlist(new_models, target_path)
        return True, new_models, saved_path

    return changed, new_models, target_path
