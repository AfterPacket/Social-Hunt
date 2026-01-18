from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


def _project_root() -> Path:
    # Anchor to this file so it works regardless of the process working directory.
    return Path(__file__).resolve().parent.parent


def _settings_path() -> Path:
    # Allow override; otherwise store in ./data/settings.json
    env = os.getenv("SOCIAL_HUNT_SETTINGS_PATH", "").strip()
    if env:
        p = Path(env)
        return p if p.is_absolute() else (_project_root() / p)
    return _project_root() / "data" / "settings.json"


def get_setting(key: str, default: Any = None) -> Any:
    """Get a setting value.

    Resolution order:
      1) data/settings.json (or SOCIAL_HUNT_SETTINGS_PATH)
      2) environment variables: KEY, KEY uppercased, SOCIAL_HUNT_<KEY uppercased>

    This is intentionally small so providers can safely read API keys/config.
    """

    k = (key or "").strip()
    if not k:
        return default

    # file
    try:
        p = _settings_path()
        if p.exists():
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and k in data:
                return data.get(k)
    except Exception:
        pass

    # env fallbacks
    for ek in (k, k.upper(), f"SOCIAL_HUNT_{k.upper()}"):
        v = os.getenv(ek)
        if v is not None and v != "":
            return v

    return default
