from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List
import os

import yaml

from .addons_base import BaseAddon
from .plugin_loader import load_python_plugin_addons


def load_plugin_addons() -> Dict[str, BaseAddon]:
    """Load addons from social_hunt.addons.*"""
    addons: Dict[str, BaseAddon] = {}
    pkg = importlib.import_module("social_hunt.addons")

    for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        try:
            mod = importlib.import_module(m.name)
        except BaseException as e:
            print(f"[WARN] Skipping addon module {m.name!r}: {e}")
            continue

        if hasattr(mod, "get_addons"):
            for a in mod.get_addons():
                if isinstance(a, BaseAddon) and a.name:
                    addons[a.name] = a

        if hasattr(mod, "ADDONS"):
            for a in getattr(mod, "ADDONS"):
                if isinstance(a, BaseAddon) and a.name:
                    addons[a.name] = a

    return addons


def build_addon_registry() -> Dict[str, BaseAddon]:
    reg = load_plugin_addons()
    allow_py = (os.getenv("SOCIAL_HUNT_ALLOW_PY_PLUGINS", "").strip() == "1")
    # Optional python addons dropped into ./plugins/python/addons/*.py
    reg.update(load_python_plugin_addons(allow=allow_py))
    return reg


def list_addon_names(registry: Dict[str, BaseAddon]) -> List[str]:
    return sorted(registry.keys())


def load_enabled_addons(path: str = "addons.yaml") -> List[str]:
    """Load enabled addon names from addons.yaml.

    Format:
      addons:
        - bio_links
        - avatar_fingerprint
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return []
    except Exception:
        return []

    addons = data.get("addons")
    if not isinstance(addons, list):
        return []
    return [str(x).strip() for x in addons if str(x).strip()]
