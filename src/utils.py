"""Utility functions for the EEG price analysis tool."""
import os
import yaml
from pathlib import Path
from typing import Dict


def load_config(config_path: str = "config.yaml") -> Dict:
    """Load configuration from YAML file.

    Values in config.local.yaml override config.yaml (gitignored — put secrets there).
    The env var HA_TOKEN overrides homeassistant.token from either file.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    local_path = Path(config_path).with_stem(Path(config_path).stem + ".local")
    if local_path.exists():
        with open(local_path) as f:
            local = yaml.safe_load(f) or {}
        _deep_merge(config, local)

    env_token = os.environ.get('HA_TOKEN')
    if env_token:
        config.setdefault('homeassistant', {})['token'] = env_token

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place (nested dicts are merged, not replaced)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def ensure_dir(path: Path) -> None:
    """Ensure a directory exists.
    
    Args:
        path: Path to directory
    """
    path.mkdir(parents=True, exist_ok=True)

