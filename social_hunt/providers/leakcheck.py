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

API_BASE = "https://leakcheck.io/api/v2/query"


class LeakCheckProvider(BaseProvider):
    """LeakCheck.io breach data search provider (API v2).

    Searches LeakCheck's indexed breach and stealer log database.

    Input auto-detection:
      - Email: searches by email
      - Username / phone / other: auto-detected by LeakCheck

    Requires 'leakcheck_api_key' set in Settings (stored as a secret).
    Get a key at https://leakcheck.io
    """

    name = "leakcheck"
    timeout = 15
    ua_profile = "desktop_chrome"

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self._static_api_key = api_key

    def _get_api_key(self) -> Optional[str]:
        """Read key fresh from disk each call so changes take effect without restart."""
        if self._static_api_key:
            return self._static_api_key
        try:
            settings_path = resolve_path("data/settings.json")
            if settings_path.exists():
                with settings_path.open("r", encoding="utf-8") as f:
                    return json.load(f).get("leakcheck_api_key")
        except Exception:
            pass
        return None

    def build_url(self, username: str) -> str:
        return f"{API_BASE}/{username}"

    def _determine_query_type(self, term: str) -> str:
        """Determine LeakCheck query type from input format."""
        if "@" in term and "." in term:
            return "email"
        clean = (
            term.replace("+", "").replace("-", "")
            .replace(" ", "").replace("(", "").replace(")", "")
        )
        if clean.isdigit() and 7 <= len(clean) <= 15:
            return "phone"
        if "." in term and term.count(".") == 3:
            parts = term.split(".")
            if all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return "auto"
        return "auto"

    async def check(
        self, username: str, client, headers: Dict[str, str]
    ) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        api_key = self._get_api_key()
        search_term = (username or "").strip()
        url = f"{API_BASE}/{search_term}" if search_term else API_BASE

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
                error="Skipped: LeakCheck API key not set in Settings (leakcheck_api_key).",
                timestamp_iso=ts,
            )

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

        query_type = self._determine_query_type(search_term)
        profile: Dict[str, Any] = {"account": search_term, "query_type": query_type}
        evidence: Dict[str, Any] = {"leakcheck": True}

        try:
            import urllib.parse
            params: Dict[str, Any] = {"limit": 100}
            if query_type != "auto":
                params["type"] = query_type

            encoded_term = urllib.parse.quote(search_term, safe="")
            request_url = f"{API_BASE}/{encoded_term}"

            async with httpx.AsyncClient(trust_env=False) as direct_client:
                response = await direct_client.get(
                    request_url,
                    params=params,
                    timeout=self.timeout,
                    headers={
                        "X-API-Key": api_key,
                        "Accept": "application/json",
                        "User-Agent": "Social-Hunt",
                    },
                )

            elapsed = int((time.monotonic() - start) * 1000)

            if response.status_code == 200:
                raw = response.json() if response.text else {}
                success = raw.get("success", False)
                data: List[Dict[str, Any]] = raw.get("result", [])

                if not success:
                    return ProviderResult(
                        provider=self.name,
                        username=username,
                        url=url,
                        status=ResultStatus.ERROR,
                        http_status=response.status_code,
                        elapsed_ms=elapsed,
                        evidence=evidence,
                        profile=profile,
                        error=raw.get("message", "LeakCheck returned success=false."),
                        timestamp_iso=ts,
                    )

                if data:
                    result_count = len(data)
                    profile["result_count"] = result_count

                    breach_sources: set = set()
                    for rec in data:
                        src = rec.get("sources") or []
                        if isinstance(src, list):
                            for s in src:
                                name = s.get("name") if isinstance(s, dict) else str(s)
                                if name:
                                    breach_sources.add(name)
                        elif isinstance(src, str) and src:
                            breach_sources.add(src)

                    if breach_sources:
                        profile["breach_sources"] = sorted(breach_sources)

                    display_data = data[:100]
                    if is_demo_mode():
                        display_data = censor_breach_data(display_data)
                        profile["demo_mode"] = True

                    profile["raw_results"] = display_data

                    data_types_found: Dict[str, int] = {}
                    for rec in data:
                        for key, value in rec.items():
                            if value and key not in ("sources", "_id", "id"):
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
                    error="Invalid API key (401) — check leakcheck_api_key in Settings.",
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
                    error="Rate limited (429) — LeakCheck limit is 3 req/sec.",
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
                    error="LeakCheck service unavailable (503).",
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


PROVIDERS = [LeakCheckProvider()]
