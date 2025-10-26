"""Utility functions for the EEG price analysis tool."""
import yaml
from pathlib import Path
from typing import Dict


def load_config(config_path: str = "config.yaml") -> Dict:
    """Load configuration from YAML file.
    
    Args:
        config_path: Path to config file
        
    Returns:
        Configuration dictionary
    """
    with open(config_path) as f:
        return yaml.safe_load(f)


def ensure_dir(path: Path) -> None:
    """Ensure a directory exists.
    
    Args:
        path: Path to directory
    """
    path.mkdir(parents=True, exist_ok=True)

