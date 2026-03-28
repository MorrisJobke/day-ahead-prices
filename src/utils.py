"""Utility functions for the EEG price analysis tool."""
import calendar
import math
import os
import yaml
from pathlib import Path
from typing import Dict, Optional, Tuple


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

    if env_token := os.environ.get('HA_TOKEN'):
        config.setdefault('homeassistant', {})['token'] = env_token
    if env_tg_token := os.environ.get('TELEGRAM_BOT_TOKEN'):
        config.setdefault('telegram', {})['bot_token'] = env_tg_token
    if env_tg_chat := os.environ.get('TELEGRAM_CHAT_ID'):
        config.setdefault('telegram', {})['chat_id'] = env_tg_chat

    return config


def _deep_merge(base: dict, override: dict) -> None:
    """Merge override into base in-place (nested dicts are merged, not replaced)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def sunrise_sunset_utc(date_str: str, lat: float, lng: float) -> Tuple[Optional[float], Optional[float]]:
    """Return (sunrise_unix_utc, sunset_unix_utc) for a given date and location.

    Uses a simplified NOAA algorithm (accurate to ~2 minutes).
    Returns (None, None) for polar night; full-day range for polar day.
    """
    parts = date_str.split('-')
    midnight_utc = calendar.timegm((int(parts[0]), int(parts[1]), int(parts[2]), 0, 0, 0))

    j2000_noon = 946728000
    n = (midnight_utc + 43200 - j2000_noon) / 86400.0

    L = (280.460 + 0.9856474 * n) % 360
    g = math.radians((357.528 + 0.9856003 * n) % 360)

    lam = math.radians(L + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.0000004 * n)
    dec = math.asin(math.sin(eps) * math.sin(lam))

    ra_deg = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360
    eot_h = ((L - ra_deg + 180) % 360 - 180) / 15.0

    solar_noon_h = 12.0 - lng / 15.0 - eot_h
    lat_r = math.radians(lat)
    cos_ha = (math.cos(math.radians(90.833)) - math.sin(lat_r) * math.sin(dec)) / \
             (math.cos(lat_r) * math.cos(dec))

    if cos_ha <= -1:
        return float(midnight_utc), float(midnight_utc + 86400)
    if cos_ha >= 1:
        return None, None

    ha_h = math.degrees(math.acos(cos_ha)) / 15.0
    sunrise = midnight_utc + (solar_noon_h - ha_h) * 3600.0
    sunset = midnight_utc + (solar_noon_h + ha_h) * 3600.0
    return sunrise, sunset


def ensure_dir(path: Path) -> None:
    """Ensure a directory exists.
    
    Args:
        path: Path to directory
    """
    path.mkdir(parents=True, exist_ok=True)

