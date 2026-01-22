from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Dict, List

import yaml

from .paths import resolve_path
from .providers_base import BaseProvider
from .providers_yaml import PatternProvider


def load_yaml_providers(path: str = "providers.yaml") -> Dict[str, BaseProvider]:
    p = resolve_path(path)
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    providers: Dict[str, BaseProvider] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict) or "url" not in cfg:
            continue
        providers[str(name)] = PatternProvider(str(name), cfg)
    return providers


def load_yaml_providers_from_dir(
    dir_path: str = "plugins/providers",
) -> Dict[str, BaseProvider]:
    """Load additional providers from YAML files in plugins/providers/*.yml|*.yaml

    Path is resolved relative to the project root unless absolute.
    """
    providers: Dict[str, BaseProvider] = {}
    d = resolve_path(dir_path)
    if not d.exists() or not d.is_dir():
        return providers

    for p in sorted(list(d.glob("*.yml")) + list(d.glob("*.yaml"))):
        try:
            with p.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                continue
            for name, cfg in data.items():
                if not isinstance(cfg, dict) or "url" not in cfg:
                    continue
                providers[str(name)] = PatternProvider(str(name), cfg)
        except Exception:
            # plugin YAML should never take down the app
            continue

    return providers


def load_plugin_providers() -> Dict[str, BaseProvider]:
    """Load any providers from social_hunt.providers.* (Python providers shipped with repo)."""
    providers: Dict[str, BaseProvider] = {}
    pkg = importlib.import_module("social_hunt.providers")

    for m in pkgutil.iter_modules(pkg.__path__, pkg.__name__ + "."):
        mod = importlib.import_module(m.name)

        if hasattr(mod, "get_providers"):
            for p in mod.get_providers():
                if isinstance(p, BaseProvider):
                    providers[p.name] = p

        if hasattr(mod, "PROVIDERS"):
            for p in getattr(mod, "PROVIDERS"):
                if isinstance(p, BaseProvider):
                    providers[p.name] = p

    return providers


def build_registry(yaml_path: str = "providers.yaml") -> Dict[str, BaseProvider]:
    reg = load_yaml_providers(yaml_path)
    # YAML plugin packs from plugins/providers override base YAML if same key
    reg.update(load_yaml_providers_from_dir("plugins/providers"))
    # Python providers override YAML entries if same name
    reg.update(load_plugin_providers())
    return reg


def list_provider_names(registry: Dict[str, BaseProvider]) -> List[str]:
    return sorted(registry.keys())
