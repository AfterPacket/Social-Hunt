from __future__ import annotations

import json
import os
from typing import Any, Dict

SECRET_HINTS = ("key", "token", "secret", "password")


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


def mask_for_client(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in data.items():
        if is_secret_key(str(k)):
            out[str(k)] = {"is_set": bool(v), "value": None, "secret": True}
        else:
            out[str(k)] = {"is_set": bool(v), "value": v, "secret": False}
    return out
