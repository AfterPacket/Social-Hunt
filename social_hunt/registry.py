from __future__ import annotations

import importlib
import pkgutil
from typing import Dict, List

import yaml

from .providers_yaml import PatternProvider
from .providers_base import BaseProvider
from .plugin_loader import load_yaml_plugin_providers, load_python_plugin_providers
import os


def load_yaml_providers(path: str = "providers.yaml") -> Dict[str, BaseProvider]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    providers: Dict[str, BaseProvider] = {}
    for name, cfg in data.items():
        if not isinstance(cfg, dict) or "url" not in cfg:
            continue
        providers[str(name)] = PatternProvider(str(name), cfg)
    return providers


def load_plugin_providers() -> Dict[str, BaseProvider]:
    """Load any providers from social_hunt.providers.*"""
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

    # Data-only provider packs dropped into ./plugins/providers/*.yaml
    reg.update(load_yaml_plugin_providers())

    # Optional python plugins dropped into ./plugins/python/providers/*.py
    allow_py = (os.getenv("SOCIAL_HUNT_ALLOW_PY_PLUGINS", "").strip() == "1")
    reg.update(load_python_plugin_providers(allow=allow_py))

    # Built-in python providers shipped with the app
    reg.update(load_plugin_providers())  # built-ins override YAML entries if same name
    return reg


def list_provider_names(registry: Dict[str, BaseProvider]) -> List[str]:
    return sorted(registry.keys())
