from __future__ import annotations

import json
import os
from typing import Any, Dict

SECRET_HINTS = ("key", "token", "secret", "password")
SECRET_KEYS_FIELD = "__secret_keys"


def is_secret_key(k: str) -> bool:
    lk = k.lower()
    return any(h in lk for h in SECRET_HINTS)


class SettingsStore:
    def __init__(self, path: str):
        self.path = path

    def load(self) -> Dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except FileNotFoundError:
            return {}
        except Exception:
            return {}

    def save(self, data: Dict[str, Any]) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        os.replace(tmp, self.path)


def _extract_secret_keys(data: Dict[str, Any]) -> set[str]:
    raw = data.get(SECRET_KEYS_FIELD)
    if isinstance(raw, list):
        return {str(x) for x in raw if str(x).strip()}
    return set()


def mask_for_client(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    secret_keys = _extract_secret_keys(data)
    for k, v in data.items():
        key = str(k)
        if key == SECRET_KEYS_FIELD:
            continue
        is_secret = key in secret_keys or is_secret_key(key)
        if is_secret:
            out[key] = {"is_set": bool(v), "value": None, "secret": True}
        else:
            out[key] = {"is_set": bool(v), "value": v, "secret": False}
    return out
