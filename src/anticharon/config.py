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


def get_data_dir() -> Path:
    """Get the active data storage directory."""
    if "ANTICHARON_DATA_DIR" in os.environ:
        path = Path(os.environ["ANTICHARON_DATA_DIR"]).expanduser()
    else:
        # Default to ~/.hermes/price_tracker/ or fallback to local ./data
        hermes_dir = Path.home() / ".hermes" / "price_tracker"
        if hermes_dir.parent.exists():
            path = hermes_dir
        else:
            path = Path("data")
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    """Resolve the path to shortlist.json configuration."""
    if "ANTICHARON_CONFIG" in os.environ:
        return Path(os.environ["ANTICHARON_CONFIG"]).expanduser()

    hermes_config = Path.home() / ".hermes" / "price_tracker" / "shortlist.json"
    if hermes_config.exists():
        return hermes_config

    local_config = Path("config/shortlist.json")
    if local_config.exists():
        return local_config

    example_config = Path("config/shortlist.example.json")
    if example_config.exists():
        return example_config

    return hermes_config


def get_history_path() -> Path:
    """Resolve the path to history.csv storage."""
    return get_data_dir() / "history.csv"


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
