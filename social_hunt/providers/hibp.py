from __future__ import annotations

import asyncio
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..paths import resolve_path
from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class HIBPProvider(BaseProvider):
    """
    Have I Been Pwned (HIBP) provider.
    Requires an API key set in settings.json (key: "hibp_api_key").
    """

    name = "hibp"
    timeout = 15
    ua_profile = "desktop_chrome"
    api_key: Optional[str] = None

    def __init__(self, api_key: Optional[str] = None):
        super().__init__()
        self.api_key = api_key
        if not self.api_key:
            try:
                settings_path = resolve_path("data/settings.json")
                if settings_path.exists():
                    with settings_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                        self.api_key = data.get("hibp_api_key")
            except Exception:
                pass

    def build_url(self, username: str) -> str:
        # HIBP is email-based, so the "username" is the email address.
        return f"https://haveibeenpwned.com/api/v3/breachedaccount/{username}"

    async def check(
        self, username: str, client, headers: Dict[str, str]
    ) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        url = self.build_url(username)

        # 1. API Key Check
        if not self.api_key:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.UNKNOWN,
                error="Skipped: HIBP API key not set in Settings (hibp_api_key).",
                timestamp_iso=ts,
            )

        # 2. Input Validation (must be an email)
        if "*" in username:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.ERROR,
                error="HIBP does not support wildcard searches.",
                timestamp_iso=ts,
            )

        if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", username):
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.NOT_FOUND,
                error="Invalid format: HIBP requires an email address.",
                timestamp_iso=ts,
            )

        hibp_headers = dict(headers)
        hibp_headers["hibp-api-key"] = self.api_key
        hibp_headers["user-agent"] = "Social-Hunt"

        profile: Dict[str, Any] = {}
        evidence: Dict[str, Any] = {}

        try:
            # 3. Perform Breach and Paste lookups in parallel
            breach_url = f"https://haveibeenpwned.com/api/v3/breachedaccount/{username}"
            paste_url = f"https://haveibeenpwned.com/api/v3/pasteaccount/{username}"

            breach_res, paste_res = await asyncio.gather(
                client.get(
                    breach_url,
                    timeout=self.timeout,
                    headers=hibp_headers,
                    follow_redirects=True,
                ),
                client.get(
                    paste_url,
                    timeout=self.timeout,
                    headers=hibp_headers,
                    follow_redirects=True,
                ),
            )

            # --- Process Breach Results ---
            if breach_res.status_code == 200:
                breaches = breach_res.json()
                profile["breach_count"] = len(breaches)
                profile["breaches"] = [b["Name"] for b in breaches]
                evidence["breaches_found"] = True
            elif breach_res.status_code == 429:
                profile["breach_error"] = "Rate limited"
            elif breach_res.status_code != 404:
                profile["breach_error"] = f"Unexpected status: {breach_res.status_code}"

            # --- Process Paste Results ---
            if paste_res.status_code == 200:
                pastes = paste_res.json()
                profile["paste_count"] = len(pastes)
                evidence["pastes_found"] = True
            elif paste_res.status_code == 429:
                profile["paste_error"] = "Rate limited"
            elif paste_res.status_code != 404:
                profile["paste_error"] = f"Unexpected status: {paste_res.status_code}"

            # Determine overall status
            if evidence.get("breaches_found") or evidence.get("pastes_found"):
                status = ResultStatus.FOUND
            elif breach_res.status_code == 429 or paste_res.status_code == 429:
                status = ResultStatus.BLOCKED
            elif breach_res.status_code == 404 and paste_res.status_code == 404:
                status = ResultStatus.NOT_FOUND
            elif breach_res.status_code >= 500 or paste_res.status_code >= 500:
                status = ResultStatus.ERROR
            else:
                status = ResultStatus.UNKNOWN

            error_msg = None
            if status == ResultStatus.BLOCKED:
                error_msg = "HIBP API Rate Limit Exceeded (429)."
            elif status == ResultStatus.ERROR:
                error_msg = f"HIBP API Error (Breach: {breach_res.status_code}, Paste: {paste_res.status_code})"

            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=status,
                error=error_msg,
                http_status=breach_res.status_code,  # Report primary status
                elapsed_ms=int((time.monotonic() - start) * 1000),
                evidence=evidence,
                profile=profile,
                timestamp_iso=ts,
            )

        except Exception as e:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.ERROR,
                error=str(e),
                timestamp_iso=ts,
            )


PROVIDERS = [HIBPProvider()]
