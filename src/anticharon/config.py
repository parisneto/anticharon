"""Configuration management and path resolution for Anticharon."""

import json
import os
from pathlib import Path
from typing import Any

DEFAULT_SHORTLIST: list[str] = [
    "openai/gpt-5.6-luna",
    "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-v4-flash-0423",
    "qwen/qwen3.7-flash",
    "google/gemini-3.1-flash-lite",
    "minimax/minimax-m2.7",
    "google/gemini-2.5-flash-lite"
]

# Interim, provisional default cache-hit-rate: no equivalent public paper covers this
# third dimension the way TraceLab justified the prompt/completion split below, so this
# is pooled from the two real activity-log samples in docs/sample/ (70,516,104 cached
# tokens over 91,973,374 total prompt tokens). Backlog: replace with a documented
# public source once one exists (docs/plans/pricing-engine-v2/PLAN.md, Deferred).
DEFAULT_CACHE_HIT_RATE = 0.766701

# TraceLab-cited 2-way split (weight_prompt=0.9971/weight_completion=0.0029), decomposed
# into the cache-aware 3-way default: weight_cached = 0.9971 * DEFAULT_CACHE_HIT_RATE,
# weight_uncached = 0.9971 * (1 - DEFAULT_CACHE_HIT_RATE), weight_completion unchanged.
DEFAULT_CONFIG: dict[str, Any] = {
    "shortlist": DEFAULT_SHORTLIST,
    "weight_uncached_prompt": 0.232622,
    "weight_cached_prompt": 0.764478,
    "weight_completion": 0.0029,
    "spike_threshold_pct": 20.0,
    "min_tracking_days_for_profile": 14,
    # Cap on how many `model discover --zdr` candidates get a live per-endpoint ZDR
    # check in one command. Applied *after* local filters narrow the candidate list
    # (see discovery.py's apply_zdr_filter) -- never silently truncated past this
    # without a warning.
    "max_zdr_check_count": 10
}


def get_data_dir(custom_dir: Path | str | None = None) -> Path:
    """Get the active data storage directory.
    
    Resolution Priority:
    1. Explicit argument (`custom_dir` or CLI `--data-dir`)
    2. Environment variable `ANTICHARON_DATA_DIR`
    3. Local `./data/` if running within project repository
    4. XDG data directory `$XDG_DATA_HOME/anticharon/` or `~/.local/share/anticharon/`
    5. User home directory `~/.anticharon/` for standalone tool/MCP execution
    """
    if custom_dir:
        path = Path(custom_dir).expanduser()
    elif "ANTICHARON_DATA_DIR" in os.environ:
        path = Path(os.environ["ANTICHARON_DATA_DIR"]).expanduser()
    elif Path("pyproject.toml").exists() or Path("config").exists():
        path = Path("data")
    elif "XDG_DATA_HOME" in os.environ:
        path = Path(os.environ["XDG_DATA_HOME"]).expanduser() / "anticharon"
    elif (Path.home() / ".local" / "share" / "anticharon").exists():
        path = Path.home() / ".local" / "share" / "anticharon"
    else:
        path = Path.home() / ".anticharon"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Fall back to /tmp/anticharon in read-only / strictly sandboxed environments
        path = Path("/tmp/anticharon")
        path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path(custom_path: Path | str | None = None) -> Path:
    """Resolve the path to shortlist.json configuration.
    
    Resolution Priority:
    1. Explicit argument (`custom_path` or CLI `--config`)
    2. Environment variable `ANTICHARON_CONFIG`
    3. Local `./config/shortlist.json` (or `./config/shortlist.example.json`)
    4. XDG user config `$XDG_CONFIG_HOME/anticharon/shortlist.json` or `~/.config/anticharon/shortlist.json`
    5. User home directory `~/.anticharon/shortlist.json`
    """
    if custom_path:
        return Path(custom_path).expanduser()
    if "ANTICHARON_CONFIG" in os.environ:
        return Path(os.environ["ANTICHARON_CONFIG"]).expanduser()

    local_config = Path("config/shortlist.json")
    if local_config.exists():
        return local_config

    example_config = Path("config/shortlist.example.json")
    if example_config.exists():
        return example_config

    # Check XDG config directory
    xdg_config_dir = Path(os.environ["XDG_CONFIG_HOME"]).expanduser() if "XDG_CONFIG_HOME" in os.environ else Path.home() / ".config"
    xdg_config = xdg_config_dir / "anticharon" / "shortlist.json"
    if xdg_config.exists():
        return xdg_config

    home_config = Path.home() / ".anticharon" / "shortlist.json"
    if home_config.exists():
        return home_config

    # If within repo, default to local config
    if Path("pyproject.toml").exists():
        return local_config

    return home_config


def get_history_path(custom_data_dir: Path | str | None = None) -> Path:
    """Resolve the path to history.csv storage."""
    return get_data_dir(custom_data_dir) / "history.csv"


def _entry_list(raw: list[Any], legacy_source: str = "manual") -> list[dict[str, Any]]:
    entries = []
    for index, item in enumerate(raw):
        if isinstance(item, str):
            entry = {"model": item, "source": legacy_source}
            if legacy_source == "hermes":
                entry["order"] = index
            entries.append(entry)
        elif isinstance(item, dict) and isinstance(item.get("model"), str):
            entry = {"model": item["model"], "source": item.get("source", "manual")}
            if "order" in item:
                entry["order"] = item["order"]
            entries.append(entry)
    return entries


def default_model(entries: list[dict[str, Any]]) -> str | None:
    """Return the explicitly ordered Hermes or manual default, if configured."""
    defaults = [entry for entry in entries if entry.get("order") == 0
                and entry.get("source") in {"hermes", "manual"}]
    hermes = next((entry for entry in defaults if entry.get("source") == "hermes"), None)
    return (hermes or (defaults[0] if defaults else None) or {}).get("model")


def load_config(config_path: Path | None = None, *, legacy_source: str = "manual") -> dict[str, Any]:
    """Load configuration from JSON file or return default fallback."""
    path = config_path or get_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge with default keys to ensure completeness
                config = dict(DEFAULT_CONFIG)
                config.update(data)
                entries = _entry_list(data.get("shortlist", DEFAULT_SHORTLIST), legacy_source)
                config["_shortlist_entries"] = entries
                config["shortlist"] = [entry["model"] for entry in entries]
                return config
        except Exception:
            pass
    config = dict(DEFAULT_CONFIG)
    config["_shortlist_entries"] = _entry_list(DEFAULT_SHORTLIST, legacy_source)
    return config


def update_config_weights(
    weight_uncached_prompt: float,
    weight_cached_prompt: float,
    weight_completion: float,
    config_path: Path | None = None
) -> Path:
    """Update the cache-aware 3-way token weights in the configuration file."""
    path = config_path or get_config_path()
    config = load_config(path)
    config["weight_uncached_prompt"] = round(weight_uncached_prompt, 6)
    config["weight_cached_prompt"] = round(weight_cached_prompt, 6)
    config["weight_completion"] = round(weight_completion, 6)
    config["shortlist"] = config.pop("_shortlist_entries", _entry_list(config.get("shortlist", [])))

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return path


def update_config_shortlist(
    shortlist: list[str] | list[dict[str, Any]],
    config_path: Path | None = None,
    *, entries: list[dict[str, Any]] | None = None,
) -> Path:
    """Update model shortlist in the configuration file."""
    path = config_path or get_config_path()
    config = load_config(path)
    normalized = _entry_list(entries if entries is not None else shortlist)
    config["shortlist"] = normalized
    config.pop("_shortlist_entries", None)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return path
