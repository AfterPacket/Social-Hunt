import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Union

_DEMO_CACHE = {"value": None, "ts": 0.0, "mtime": None}
_CACHE_TTL_SEC = 2.0


def _settings_path() -> Path:
    env_path = (os.getenv("SOCIAL_HUNT_SETTINGS_PATH") or "").strip()
    if env_path:
        p = Path(env_path)
    else:
        p = Path("data/settings.json")
    return p if p.is_absolute() else (Path(__file__).resolve().parents[1] / p)


def _read_demo_mode_from_settings() -> bool | None:
    path = _settings_path()
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    except Exception:
        return None

    now = time.time()
    cached = _DEMO_CACHE
    if cached["value"] is not None and cached["mtime"] == mtime:
        if now - float(cached["ts"]) < _CACHE_TTL_SEC:
            return cached["value"]

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    val = None
    if isinstance(raw, dict):
        val = raw.get("demo_mode")

    demo = None
    if isinstance(val, bool):
        demo = val
    elif isinstance(val, (int, float)):
        demo = bool(int(val))
    elif isinstance(val, str):
        demo = val.strip().lower() in ("1", "true", "yes", "on")

    cached["value"] = demo
    cached["ts"] = now
    cached["mtime"] = mtime
    return demo


def is_demo_mode() -> bool:
    """Check if the application is running in demo mode."""
    env = os.getenv("SOCIAL_HUNT_DEMO_MODE")
    if env is not None and env.strip() != "":
        return env.strip().lower() in ("1", "true", "yes", "on")

    val = _read_demo_mode_from_settings()
    return bool(val)


def censor_value(value: Any, key: str = "") -> Any:
    """
    Censors sensitive information by masking characters.

    Args:
        value: The value to censor.
        key: The field name/key associated with the value.
    """
    if not is_demo_mode() or value is None:
        return value

    if not isinstance(value, str):
        return value

    # Don't censor short metadata or known safe keys
    safe_keys = {
        "source",
        "breach",
        "database",
        "origin",
        "status",
        "provider",
        "elapsed_ms",
        "result_count",
        "breach_sources",
        "data_types",
        "note",
        "demo_mode",
        "fields_searched",
        "account",
        "username",
        "query",
        "type",
        "category",
    }
    if key.lower() in safe_keys:
        return value

    # Email censoring: u***@domain.com
    if "@" in value and "." in value:
        parts = value.split("@")
        if len(parts) == 2:
            name, domain = parts
            censored_name = name[0] + "***" if len(name) > 1 else "*"
            return f"{censored_name}@{domain}"

    # Generic string censoring: keeps first 2 chars, masks the rest
    if len(value) <= 2:
        return "*" * len(value)

    # Keep a bit more for context if it's a long string, but mask the core
    prefix_len = 2
    return value[:prefix_len] + "*" * 8


def censor_breach_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Iterates through breach records and censors personal information.
    Limits results to 5 in demo mode to show functionality without giving away all data.
    """
    if not is_demo_mode():
        return data

    # Limit results for demo
    demo_limit = 5
    limited_data = data[:demo_limit]

    censored_results = []
    for record in limited_data:
        censored_record = {}
        for k, v in record.items():
            censored_record[k] = censor_value(v, k)
        censored_results.append(censored_record)

    return censored_results
