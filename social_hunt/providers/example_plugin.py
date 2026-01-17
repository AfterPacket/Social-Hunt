from __future__ import annotations

import time
from datetime import datetime, timezone

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus

class ExampleProvider(BaseProvider):
    name = "example"
    timeout = 10
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        return f"https://example.com/{username}"

    async def check(self, username: str, client, headers):
        url = self.build_url(username)
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()

        try:
            r = await client.get(url, timeout=self.timeout, follow_redirects=True, headers=headers)
            text = (r.text or "").lower()
            if "not found" in text:
                status = ResultStatus.NOT_FOUND
            elif username.lower() in text:
                status = ResultStatus.FOUND
            else:
                status = ResultStatus.UNKNOWN

            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=status,
                http_status=r.status_code,
                elapsed_ms=int((time.monotonic() - start) * 1000),
                evidence={"len": len(text)},
                profile={},
                timestamp_iso=ts,
            )
        except Exception as e:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.ERROR,
                error=str(e),
                elapsed_ms=int((time.monotonic() - start) * 1000),
                profile={},
                timestamp_iso=ts,
            )

PROVIDERS = [ExampleProvider()]
