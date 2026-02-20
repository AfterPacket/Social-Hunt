from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from ..demo import censor_breach_data, is_demo_mode
from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class BreachVIPProvider(BaseProvider):
    """BreachVIP breach data search provider.

    Searches for data across multiple fields in the BreachVIP database.

    Input:
      - Username/Email/Phone/DiscordID/etc: searches across relevant fields

    Rate limit: 15 requests per minute
    Maximum results: 10,000 per search

    No API key or settings required.
    """

    name = "breachvip"
    timeout = 15
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        return "https://breach.vip/api/search"

    def _determine_search_fields(self, search_term: str) -> List[str]:
        """Determine which fields to search based on the input format."""
        # Default fields
        fields = ["username", "email", "name"]

        if "@" in search_term and "." in search_term:
            fields = ["email", "username", "name"]
        elif "." in search_term and "@" not in search_term:
            fields.append("domain")

        clean = (
            search_term.replace("+", "")
            .replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )
        if clean.isdigit() and 7 <= len(clean) <= 15:
            fields.append("phone")

        if search_term.isdigit() and 17 <= len(search_term) <= 20:
            fields.append("discordid")

        if len(search_term) == 36 and "-" in search_term:
            fields.append("uuid")

        if "." in search_term and search_term.count(".") == 3:
            parts = search_term.split(".")
            if all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                fields.append("ip")

        fields.append("password")
        return list(dict.fromkeys(fields))[:10]

    async def check(
        self, username: str, client, headers: Dict[str, str]
    ) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()

        search_term = (username or "").strip()
        if not search_term:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=0,
                evidence={"breachvip": True},
                profile={},
                error="empty input",
                timestamp_iso=ts,
            )

        breachvip_headers = dict(headers)
        breachvip_headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "DNT": "1",
                "Host": "breach.vip",
                "Origin": "https://breach.vip",
                "Pragma": "no-cache",
                "Referer": "https://breach.vip/",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        fields_to_search = self._determine_search_fields(search_term)
        is_wildcard = "*" in search_term

        request_body = {
            "term": search_term,
            "fields": fields_to_search,
            "categories": [],
            "wildcard": is_wildcard,
            "case_sensitive": False,
        }

        profile: Dict[str, Any] = {
            "account": search_term,
            "fields_searched": fields_to_search,
        }
        evidence: Dict[str, Any] = {"breachvip": True}

        try:
            async with httpx.AsyncClient(trust_env=False) as direct_client:
                response = await direct_client.post(
                    self.build_url(username),
                    timeout=self.timeout,
                    headers=breachvip_headers,
                    json=request_body,
                )

            elapsed = int((time.monotonic() - start) * 1000)

            if response.status_code == 200:
                raw_json = response.json() if response.text else []
                data = []

                if isinstance(raw_json, dict):
                    if "results" in raw_json and isinstance(raw_json["results"], list):
                        data = raw_json["results"]
                    elif "data" in raw_json and isinstance(raw_json["data"], list):
                        data = raw_json["data"]
                    else:
                        data = [raw_json]
                elif isinstance(raw_json, list):
                    data = raw_json

                if (
                    isinstance(data, list)
                    and len(data) == 1
                    and isinstance(data[0], dict)
                ):
                    inner = data[0]
                    if "results" in inner and isinstance(inner["results"], list):
                        data = inner["results"]
                    elif "data" in inner and isinstance(inner["data"], list):
                        data = inner["data"]

                if data:
                    result_count = len(data)
                    breach_sources = set()
                    for result in data:
                        if isinstance(result, dict):
                            for field in ["source", "breach", "database", "origin"]:
                                if field in result and result[field]:
                                    breach_sources.add(str(result[field]))

                    profile["result_count"] = result_count
                    if breach_sources:
                        profile["breach_sources"] = list(breach_sources)

                    display_data = data[:100]
                    if is_demo_mode():
                        display_data = censor_breach_data(data)
                        profile["demo_mode"] = True

                    profile["raw_results"] = display_data

                    data_types_found: Dict[str, int] = {}
                    for result in data:
                        if isinstance(result, dict):
                            for key, value in result.items():
                                if value and key not in (
                                    "_id", "id", "index", "source",
                                    "breach", "database", "origin",
                                ):
                                    data_types_found[key] = (
                                        data_types_found.get(key, 0) + 1
                                    )

                    if data_types_found:
                        profile["data_types"] = data_types_found

                    if result_count >= 10000:
                        profile["note"] = "Result limit reached (10,000+)"

                    return ProviderResult(
                        provider=self.name,
                        username=username,
                        url=self.build_url(username),
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
                        url=self.build_url(username),
                        status=ResultStatus.NOT_FOUND,
                        http_status=response.status_code,
                        elapsed_ms=elapsed,
                        evidence=evidence,
                        profile=profile,
                        timestamp_iso=ts,
                    )

            elif response.status_code == 400:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.ERROR,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Bad request - check search parameters",
                    timestamp_iso=ts,
                )

            elif response.status_code == 403:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.BLOCKED,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Access Denied (Cloudflare). Your server IP might be flagged. Try searching manually at breach.vip.",
                    timestamp_iso=ts,
                )

            elif response.status_code == 405:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.ERROR,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Method not allowed",
                    timestamp_iso=ts,
                )

            elif response.status_code == 429:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.BLOCKED,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Rate limited (15 requests/minute) - wait 1 minute",
                    timestamp_iso=ts,
                )

            elif response.status_code == 503:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.BLOCKED,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Service unavailable (503) - breach.vip may be down or blocking requests",
                    timestamp_iso=ts,
                )

            elif response.status_code == 500:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.ERROR,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error="Internal server error",
                    timestamp_iso=ts,
                )

            else:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.UNKNOWN,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    error=f"Unexpected response ({response.status_code})",
                    timestamp_iso=ts,
                )

        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=elapsed,
                evidence=evidence,
                profile=profile,
                error=str(e),
                timestamp_iso=ts,
            )


PROVIDERS = [BreachVIPProvider()]
