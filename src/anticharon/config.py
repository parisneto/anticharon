"""Configuration management and path resolution for Anticharon."""

import json
import os
from pathlib import Path
from typing import Dict, Any, List

DEFAULT_SHORTLIST: List[str] = [
    "deepseek/deepseek-v4-flash-0731",
    "deepseek/deepseek-v4-flash-0423",
    "qwen/qwen3.7-flash",
    "openai/gpt-5.6-luna",
    "google/gemini-3.1-flash-lite",
    "minimax/minimax-m2.7",
    "google/gemini-2.5-flash-lite"
]

DEFAULT_CONFIG: Dict[str, Any] = {
    "shortlist": DEFAULT_SHORTLIST,
    "weight_prompt": 0.9922,
    "weight_completion": 0.0078,
    "spike_threshold_pct": 20.0
}


def get_data_dir(custom_dir: Path | str | None = None) -> Path:
    """Get the active data storage directory.
    
    Resolution Priority:
    1. Explicit argument (`custom_dir` or CLI `--data-dir`)
    2. Environment variable `ANTICHARON_DATA_DIR`
    3. Local `./data/` if running within project repository
    4. User home directory `~/.anticharon/` for standalone tool/MCP execution
    """
    if custom_dir:
        path = Path(custom_dir).expanduser()
    elif "ANTICHARON_DATA_DIR" in os.environ:
        path = Path(os.environ["ANTICHARON_DATA_DIR"]).expanduser()
    elif Path("pyproject.toml").exists() or Path("config").exists():
        path = Path("data")
    else:
        path = Path.home() / ".anticharon"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path(custom_path: Path | str | None = None) -> Path:
    """Resolve the path to shortlist.json configuration.
    
    Resolution Priority:
    1. Explicit argument (`custom_path` or CLI `--config`)
    2. Environment variable `ANTICHARON_CONFIG`
    3. Local `./config/shortlist.json` (or `./config/shortlist.example.json`)
    4. User home directory `~/.anticharon/shortlist.json`
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


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load configuration from JSON file or return default fallback."""
    path = config_path or get_config_path()
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Merge with default keys to ensure completeness
                config = dict(DEFAULT_CONFIG)
                config.update(data)
                return config
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def update_config_weights(
    weight_prompt: float,
    weight_completion: float,
    config_path: Path | None = None
) -> Path:
    """Update prompt and completion weights in the configuration file."""
    path = config_path or get_config_path()
    config = load_config(path)
    config["weight_prompt"] = round(weight_prompt, 6)
    config["weight_completion"] = round(weight_completion, 6)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    return path
