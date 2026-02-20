from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..demo import censor_breach_data, is_demo_mode
from ..paths import resolve_path
from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus

API_URL = "https://api.snusbase.com/data/search"

SEARCH_TYPES = {
    "email": ["email"],
    "username": ["username"],
    "phone": ["username", "email"],
    "ip": ["lastip"],
    "default": ["email", "username"],
}


class SnusbaseProvider(BaseProvider):
    """Snusbase breach data search provider.

    Searches across Snusbase's indexed breach database.

    Input:
      - Email: searches email field
      - Username: searches username field
      - IP: searches lastip field
      - Other: searches email + username

    Requires 'snusbase_api_key' set in Settings (stored as a secret).
    Rate limit: 2048 requests per day (included with paid membership).
    """

    name = "snusbase"
    timeout = 15
    ua_profile = "desktop_chrome"

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self._static_api_key = api_key  # only used if explicitly passed

    def _get_api_key(self) -> Optional[str]:
        """Read key fresh from disk each call so changes take effect without restart."""
        if self._static_api_key:
            return self._static_api_key
        try:
            settings_path = resolve_path("data/settings.json")
            if settings_path.exists():
                with settings_path.open("r", encoding="utf-8") as f:
                    return json.load(f).get("snusbase_api_key")
        except Exception:
            pass
        return None

    def build_url(self, username: str) -> str:
        return API_URL

    def _determine_types(self, term: str) -> List[str]:
        if "@" in term and "." in term:
            return ["email"]
        clean = (
            term.replace("+", "").replace("-", "")
            .replace(" ", "").replace("(", "").replace(")", "")
        )
        if clean.isdigit() and 7 <= len(clean) <= 15:
            return ["username", "email"]
        if "." in term and term.count(".") == 3:
            parts = term.split(".")
            if all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return ["lastip"]
        return ["email", "username"]

    async def check(
        self, username: str, client, headers: Dict[str, str]
    ) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        url = API_URL
        api_key = self._get_api_key()

        if not api_key:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.UNKNOWN,
                http_status=None,
                elapsed_ms=0,
                evidence={},
                profile={},
                error="Skipped: Snusbase API key not set in Settings (snusbase_api_key).",
                timestamp_iso=ts,
            )

        search_term = (username or "").strip()
        if not search_term:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=0,
                evidence={},
                profile={},
                error="Empty input.",
                timestamp_iso=ts,
            )

        types = self._determine_types(search_term)
        profile: Dict[str, Any] = {"account": search_term, "types_searched": types}
        evidence: Dict[str, Any] = {"snusbase": True}

        try:
            async with httpx.AsyncClient(trust_env=False) as direct_client:
                response = await direct_client.post(
                    url,
                    timeout=self.timeout,
                    headers={
                        "Auth": api_key,
                        "Content-Type": "application/json",
                    },
                    json={"terms": [search_term], "types": types},
                )

            elapsed = int((time.monotonic() - start) * 1000)

            if response.status_code == 200:
                raw = response.json() if response.text else {}
                # Flatten results from all databases into a single list
                results_by_db: Dict[str, Any] = raw.get("results", {})
                data: List[Dict[str, Any]] = []
                for db_name, records in results_by_db.items():
                    if isinstance(records, list):
                        for rec in records:
                            if isinstance(rec, dict):
                                rec.setdefault("_db", db_name)
                                data.append(rec)

                if data:
                    result_count = len(data)
                    breach_sources = set()
                    for rec in data:
                        db = rec.get("_db") or rec.get("source") or rec.get("breach")
                        if db:
                            breach_sources.add(str(db))

                    profile["result_count"] = result_count
                    if breach_sources:
                        profile["breach_sources"] = list(breach_sources)

                    display_data = data[:100]
                    if is_demo_mode():
                        display_data = censor_breach_data(data)
                        profile["demo_mode"] = True

                    profile["raw_results"] = display_data

                    data_types_found: Dict[str, int] = {}
                    for rec in data:
                        for key, value in rec.items():
                            if value and key not in ("_id", "_db", "id", "source", "breach"):
                                data_types_found[key] = data_types_found.get(key, 0) + 1
                    if data_types_found:
                        profile["data_types"] = data_types_found

                    return ProviderResult(
                        provider=self.name,
                        username=username,
                        url=url,
                        status=ResultStatus.FOUND,
                        http_status=response.status_code,
                        elapsed_ms=elapsed,
                        evidence=evidence,
                        profile=profile,
                        timestamp_iso=ts,
                    )
                else:
                    return ProviderResult(
                        provider=self.name,
                        username=username,
                        url=url,
                        status=ResultStatus.NOT_FOUND,
                        http_status=response.status_code,
                        elapsed_ms=elapsed,
                        evidence=evidence,
                        profile=profile,
                        timestamp_iso=ts,
                    )

            elif response.status_code == 401:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=url,
                    status=ResultStatus.ERROR,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Invalid API key (401) - check snusbase_api_key in Settings.",
                    timestamp_iso=ts,
                )

            elif response.status_code == 429:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=url,
                    status=ResultStatus.BLOCKED,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Rate limited (2048 req/day exceeded).",
                    timestamp_iso=ts,
                )

            elif response.status_code == 503:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=url,
                    status=ResultStatus.BLOCKED,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Snusbase service unavailable (503).",
                    timestamp_iso=ts,
                )

            else:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=url,
                    status=ResultStatus.UNKNOWN,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error=f"Unexpected response ({response.status_code}).",
                    timestamp_iso=ts,
                )

        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=elapsed,
                evidence=evidence,
                profile=profile,
                error=str(e),
                timestamp_iso=ts,
            )


PROVIDERS = [SnusbaseProvider()]
