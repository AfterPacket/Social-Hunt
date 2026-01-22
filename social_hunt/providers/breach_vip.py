from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class BreachVIPProvider(BaseProvider):
    """BreachVIP breach data search provider.

    Searches for data across multiple fields in the BreachVIP database.

    Input:
      - Username/Email/Phone/DiscordID/etc: searches across relevant fields

    Rate limit: 15 requests per minute
    Maximum results: 10,000 per search

    Note: No API key required based on the OpenAPI documentation.
    """

    name = "breachvip"
    timeout = 15
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        return "https://breach.vip/api/search"

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

        # Prepare request headers to mimic a browser/AJAX request
        breachvip_headers = dict(headers)
        breachvip_headers.update(
            {
                "Content-Type": "application/json",
                "Origin": "https://breach.vip",
                "Referer": "https://breach.vip/",
                "Accept": "application/json, text/plain, */*",
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
            }
        )

        # Determine which fields to search based on the input
        fields_to_search = self._determine_search_fields(search_term)

        request_body = {
            "term": search_term,
            "fields": fields_to_search,
            "categories": None,  # Only minecraft supported for now
            "wildcard": False,
            "case_sensitive": False,
        }

        profile: Dict[str, Any] = {
            "account": search_term,
            "fields_searched": fields_to_search,
        }
        evidence: Dict[str, Any] = {"breachvip": True}

        try:
            response = await client.post(
                self.build_url(username),
                timeout=self.timeout,
                headers=breachvip_headers,
                json=request_body,
            )

            elapsed = int((time.monotonic() - start) * 1000)

            if response.status_code == 200:
                data = response.json() if response.text else []

                if isinstance(data, list) and data:
                    # Found results
                    result_count = len(data)

                    # Extract unique breach sources if available
                    breach_sources = set()
                    for result in data:
                        if isinstance(result, dict):
                            # Check for common breach source fields
                            for field in ["source", "breach", "database", "origin"]:
                                if field in result and result[field]:
                                    breach_sources.add(str(result[field]))

                    profile["result_count"] = result_count
                    if breach_sources:
                        profile["breach_sources"] = list(breach_sources)

                    # Store raw results (up to 100) for detailed rendering
                    profile["raw_results"] = data[:100]

                    # Aggregate data types found across all results
                    data_types_found = {}
                    for result in data:
                        if isinstance(result, dict):
                            for key, value in result.items():
                                # Filter out metadata/structural keys
                                if value and key not in (
                                    "_id",
                                    "id",
                                    "index",
                                    "source",
                                    "breach",
                                    "database",
                                    "origin",
                                ):
                                    data_types_found[key] = (
                                        data_types_found.get(key, 0) + 1
                                    )

                    if data_types_found:
                        profile["data_types"] = data_types_found

                    # Check if we hit the 10k limit
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
                    # No results
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

    def _determine_search_fields(self, search_term: str) -> List[str]:
        """Determine which fields to search based on the input type."""
        # Start with the most common fields
        fields = ["username", "email", "name"]

        # Check for email pattern
        if "@" in search_term and "." in search_term:
            # It's likely an email, prioritize email field
            fields = ["email", "username", "name"]

        # Check for domain pattern (has dots but no @)
        elif "." in search_term and "@" not in search_term:
            fields.append("domain")

        # Check for phone number pattern
        clean_term = (
            search_term.replace("+", "")
            .replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )
        if clean_term.isdigit() and 7 <= len(clean_term) <= 15:
            fields.append("phone")

        # Check for Discord ID (18-19 digits)
        if search_term.isdigit() and 17 <= len(search_term) <= 20:
            fields.append("discordid")

        # Check for UUID pattern
        if len(search_term) == 36 and "-" in search_term:
            fields.append("uuid")

        # Check for IP address pattern
        if "." in search_term and search_term.count(".") == 3:
            parts = search_term.split(".")
            if all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
                fields.append("ip")

        # Always include password field for completeness
        fields.append("password")

        # Remove duplicates and ensure we have at most 10 fields (API limit)
        unique_fields = list(dict.fromkeys(fields))[:10]

        return unique_fields


PROVIDERS = [BreachVIPProvider()]
