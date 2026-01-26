from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, TypeVar

import yaml

from .addons_base import BaseAddon
from .paths import resolve_path
from .providers_base import BaseProvider
from .providers_yaml import PatternProvider

T = TypeVar("T")


def plugins_dir() -> Path:
    """Root plugins directory.

    Defaults to ./plugins (relative to repo root / working dir).
    """
    return resolve_path(os.getenv("SOCIAL_HUNT_PLUGINS_DIR", "plugins"))


def _safe_glob(base: Path, pattern: str) -> List[Path]:
    try:
        return [p for p in base.glob(pattern) if p.is_file()]
    except Exception:
        return []


def load_yaml_plugin_providers() -> Dict[str, BaseProvider]:
    """Load extra providers from plugins/providers/*.yaml.

    These are *data-only* provider definitions executed by PatternProvider.
    """
    root = plugins_dir() / "providers"
    providers: Dict[str, BaseProvider] = {}
    for ypath in _safe_glob(root, "*.yml") + _safe_glob(root, "*.yaml"):
        try:
            with open(ypath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            continue

        if not isinstance(data, dict):
            continue

        for name, cfg in data.items():
            if not isinstance(cfg, dict) or "url" not in cfg:
                continue
            providers[str(name)] = PatternProvider(str(name), cfg)
    return providers


def _unique_mod_name(prefix: str, path: Path) -> str:
    h = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:12]
    safe = "".join(c for c in path.stem if c.isalnum() or c in ("_", "-"))
    safe = safe.replace("-", "_")
    return f"{prefix}.{safe}_{h}"


def _import_module_from_path(prefix: str, path: Path):
    name = _unique_mod_name(prefix, path)
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    return mod


def load_python_plugin_providers(allow: bool) -> Dict[str, BaseProvider]:
    """Load provider plugins from plugins/python/providers/*.py.

    NOTE: This executes arbitrary Python in-process. Only enable if you
    trust whoever can write to your plugins directory.
    """
    if not allow:
        return {}
    root = plugins_dir() / "python" / "providers"
    out: Dict[str, BaseProvider] = {}
    for p in _safe_glob(root, "*.py"):
        try:
            mod = _import_module_from_path("social_hunt_ext.providers", p)
        except Exception:
            continue

        if hasattr(mod, "get_providers"):
            try:
                for prov in mod.get_providers():
                    if isinstance(prov, BaseProvider) and prov.name:
                        out[prov.name] = prov
            except Exception:
                pass

        if hasattr(mod, "PROVIDERS"):
            try:
                for prov in getattr(mod, "PROVIDERS"):
                    if isinstance(prov, BaseProvider) and prov.name:
                        out[prov.name] = prov
            except Exception:
                pass
    return out


def load_python_plugin_addons(allow: bool) -> Dict[str, BaseAddon]:
    """Load addon plugins from plugins/python/addons/*.py.

    NOTE: This executes arbitrary Python in-process.
    """
    if not allow:
        return {}
    root = plugins_dir() / "python" / "addons"
    out: Dict[str, BaseAddon] = {}
    for p in _safe_glob(root, "*.py"):
        try:
            mod = _import_module_from_path("social_hunt_ext.addons", p)
        except Exception:
            continue

        if hasattr(mod, "get_addons"):
            try:
                for addon in mod.get_addons():
                    if isinstance(addon, BaseAddon) and addon.name:
                        out[addon.name] = addon
            except Exception:
                pass

        if hasattr(mod, "ADDONS"):
            try:
                for addon in getattr(mod, "ADDONS"):
                    if isinstance(addon, BaseAddon) and addon.name:
                        out[addon.name] = addon
            except Exception:
                pass
    return out


def list_installed_plugins() -> Dict[str, Any]:
    """Return a simple inventory of plugin files present on disk."""
    root = plugins_dir()
    print(f"[PLUGIN_LIST] Scanning plugins root: {root} (exists={root.exists()})")

    inv: Dict[str, Any] = {
        "root": str(root),
        "yaml_providers": [],
        "python_providers": [],
        "python_addons": [],
    }
    inv["yaml_providers"] = [
        p.relative_to(root).as_posix()
        for p in (
            _safe_glob(root / "providers", "*.yaml")
            + _safe_glob(root / "providers", "*.yml")
        )
    ]
    inv["python_providers"] = [
        p.relative_to(root).as_posix()
        for p in _safe_glob(root / "python" / "providers", "*.py")
    ]
    inv["python_addons"] = [
        p.relative_to(root).as_posix()
        for p in _safe_glob(root / "python" / "addons", "*.py")
    ]

    print(
        f"[PLUGIN_LIST] Found {len(inv['yaml_providers'])} YAML, {len(inv['python_providers'])} Providers, {len(inv['python_addons'])} Addons"
    )
    return inv
