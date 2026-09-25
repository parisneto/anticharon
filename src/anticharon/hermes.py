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
from anticharon.models import AgentMessage

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

HERMES_NOT_DETECTED_TEXT = (
    "Hermes configuration not found at ~/.hermes/config.yaml or via $HERMES_HOME/$HERMES_CONFIG; "
    "operating in standalone mode with the Anticharon shortlist."
)
HERMES_CONFIG_ACTION = {
    "mcp": "import_hermes_models(hermes_config_path=\"<path to Hermes config.yaml>\")",
    "cli": "anticharon model sync --hermes-config <path> (or set $HERMES_CONFIG; use --no-hermes to silence)",
}
HERMES_SYNC_ACTION = {"mcp": "import_hermes_models(dry_run=false)", "cli": "anticharon model sync"}

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
        if proc_fallback.returncode != 0:
            # A non-zero exit on the fallback sub-query is not a legitimate
            # "no fallbacks configured" answer -- the default model query
            # already succeeded (a configuration demonstrably exists), but
            # the complete fallback set could not be established. Treat this
            # the same as unparseable-but-non-empty output: incomplete, never
            # a silently "complete" default-only result (Issue #4).
            detection = DETECTION_INCOMPLETE
        elif proc_fallback.stdout.strip():
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

    A `complete` detection is authoritative and may legitimately shrink or
    otherwise change the shortlist. An `incomplete` one must never replace an
    existing non-empty shortlist with the partial/default-only set it
    detected -- regardless of whether that partial set happens to be shorter,
    the same length, or even longer (Issue #4). Length is not a reliable
    completeness signal, so it is never used to decide this.

    Returns (changed: bool, shortlist: List[str], config_path: Path).
    """
    target_path = config_path or get_config_path()
    current_cfg = load_config(target_path, legacy_source="hermes")
    current_shortlist = current_cfg.get("shortlist", [])
    current_entries = current_cfg.get("_shortlist_entries", [])

    new_models = hermes_models.get("all_models", [])
    if not new_models:
        return False, current_shortlist, target_path

    incomplete = hermes_models.get("detection", DETECTION_COMPLETE) != DETECTION_COMPLETE
    if incomplete and current_shortlist:
        return False, current_shortlist, target_path

    manual_entries = [e for e in current_entries if e.get("source") != "hermes"]
    hermes_entries = [{"model": model, "source": "hermes", "order": index}
                      for index, model in enumerate(new_models)]
    entries = hermes_entries + manual_entries
    changed = (current_entries != entries)

    if changed and not dry_run:
        saved_path = update_config_shortlist(new_models, target_path, entries=entries)
        return True, [e["model"] for e in entries], saved_path

    return changed, [e["model"] for e in entries], target_path


def hermes_shortlist_divergent(hermes_models: list[str], shortlist: list[Any]) -> bool:
    """True when the Hermes model sequence differs from the persisted shortlist.

    Order-sensitive on purpose: Hermes resolves `fallback_providers` strictly
    top to bottom (D-5). Shared by `run`/`check`/`check_prices` and
    `anticharon test` (A2A-6). Compares the whole persisted shortlist until
    source-tagged entries exist (MCP-7), which narrow it to Hermes-sourced ones.
    """
    managed = [e.get("model") if isinstance(e, dict) else e for e in shortlist
               if not isinstance(e, dict) or e.get("source") == "hermes"]
    return list(hermes_models) != managed


def hermes_detection_messages(hermes_info: dict[str, Any] | None, shortlist: list[str]) -> list[AgentMessage]:
    """Detection-quality messages for a Hermes result against the persisted shortlist.

    `None` (no Hermes found) -> HERMES_NOT_DETECTED; incomplete ->
    HERMES_INCOMPLETE; complete but divergent -> HERMES_DIVERGENT.
    """
    if not hermes_info:
        return [AgentMessage("warning", "HERMES_NOT_DETECTED", HERMES_NOT_DETECTED_TEXT, action=HERMES_CONFIG_ACTION)]
    if hermes_info.get("detection", DETECTION_COMPLETE) != DETECTION_COMPLETE:
        return [AgentMessage("warning", "HERMES_INCOMPLETE", INCOMPLETE_DETECTION_WARNING)]
    h_models = hermes_info.get("all_models", [])
    if hermes_shortlist_divergent(h_models, shortlist):
        return [AgentMessage(
            "warning",
            "HERMES_DIVERGENT",
            f"Detected Hermes model sequence ({len(h_models)} models) differs from the persisted "
            f"Anticharon shortlist ({len(shortlist)} models); order matters for fallbacks.",
            action=HERMES_SYNC_ACTION,
        )]
    return []


def shortlist_write_message(changed: bool, dry_run: bool, what: str) -> AgentMessage:
    """PREVIEW_ONLY / SHORTLIST_UPDATED / SHORTLIST_UNCHANGED for a shortlist write (A2A-7)."""
    if dry_run:
        return AgentMessage(
            "info", "PREVIEW_ONLY",
            f"Dry run: {what} computed for preview only; shortlist.json was not modified.",
            action={"mcp": "repeat the call with dry_run=false", "cli": "repeat the command without --dry-run"},
        )
    if changed:
        return AgentMessage("info", "SHORTLIST_UPDATED", f"{what[0].upper()}{what[1:]} persisted to shortlist.json.")
    return AgentMessage("info", "SHORTLIST_UNCHANGED", f"Shortlist unchanged: {what} did not modify shortlist.json.")


def build_hermes_import_payload(
    hermes_info: dict[str, Any] | None,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], list[AgentMessage]]:
    """Payload and messages for a one-way Hermes -> Anticharon import.

    Shared by MCP `import_hermes_models` and CLI `model sync`, so both
    surfaces return the same JSON. Hermes absence is a `warning`, never an
    error (D-1e); an incomplete detection is a `warning` that preserves the
    existing shortlist (spec §6.2).
    """
    base = {"direction": "hermes→anticharon", "hermes_untouched": True}
    if not hermes_info:
        return {"status": "warning", **base, "detected": False}, hermes_detection_messages(None, [])

    changed, new_shortlist, saved_path = sync_hermes_to_config(hermes_info, config_path=config_path, dry_run=dry_run)
    detection = hermes_info.get("detection", DETECTION_COMPLETE)
    incomplete = detection != DETECTION_COMPLETE
    messages = [AgentMessage("warning", "HERMES_INCOMPLETE", INCOMPLETE_DETECTION_WARNING)] if incomplete else []
    messages.append(shortlist_write_message(changed, dry_run, f"Hermes import of {len(new_shortlist)} models"))
    payload = {
        "status": "warning" if incomplete else "success",
        **base,
        "detected": True,
        "detection": detection,
        "source": hermes_info.get("source"),
        "method": hermes_info.get("method"),
        "default_model": hermes_info.get("default_model"),
        "models_count": len(hermes_info.get("all_models", [])),
        "changed": changed,
        "dry_run": dry_run,
        "shortlist": new_shortlist,
        "config_path": str(saved_path),
    }
    return payload, messages
