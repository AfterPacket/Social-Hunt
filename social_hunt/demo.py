import os
import re
from typing import Any, Dict, List, Union

# Environment variable to toggle demo mode
SOCIAL_HUNT_DEMO_MODE = os.getenv("SOCIAL_HUNT_DEMO_MODE", "0") == "1"


def is_demo_mode() -> bool:
    """Check if the application is running in demo mode."""
    return SOCIAL_HUNT_DEMO_MODE


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
