from __future__ import annotations

import re
from typing import Dict, List, Tuple

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_HASH_LENGTHS = {32: "hash_md5", 40: "hash_sha1", 64: "hash_sha256"}


def classify_query(value: str) -> Tuple[str, str]:
    """Classify a search value without making network requests."""
    value = (value or "").strip()
    lowered = value.lower()
    if lowered.startswith(("http://", "https://")):
        return "url", value
    if _EMAIL_RE.fullmatch(value):
        return "email", value.lower()
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", value):
        if all(0 <= int(part) <= 255 for part in value.split(".")):
            return "ip", value
    compact = re.sub(r"[\s().-]", "", value)
    if re.fullmatch(r"\+?\d{7,15}", compact):
        return "phone", value
    if "." in value and " " not in value:
        return "domain", lowered.rstrip(".")
    if len(value) in _HASH_LENGTHS and re.fullmatch(r"[0-9a-fA-F]+", value):
        return _HASH_LENGTHS[len(value)], lowered
    if any(char.isspace() for char in value):
        return "name", value
    return "username", value


def select_providers(registry: Dict[str, object], query_type: str) -> List[str]:
    if query_type in {"username", "name"}:
        return list(registry.keys())
    return [
        name
        for name, provider in registry.items()
        if query_type in getattr(provider, "query_types", set())
    ]


def provider_plan(registry: Dict[str, object], query_type: str):
    selected = set(select_providers(registry, query_type))
    return [
        {
            "name": name,
            "selected": name in selected,
            "auto_enabled": bool(getattr(provider, "auto_enabled", False)),
            "query_types": sorted(getattr(provider, "query_types", {"username"})),
        }
        for name, provider in sorted(registry.items())
    ]
