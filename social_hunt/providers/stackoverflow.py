from __future__ import annotations

import re
from datetime import datetime, timezone

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class StackOverflowProvider(BaseProvider):
    name = "stackoverflow"
    timeout = 10
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        # Stack Overflow needs a user ID and an optional username.
        # This provider assumes the input is a numeric ID.
        # Format: /users/{id}/{displayname}
        clean_id = "".join(filter(str.isdigit, username))
        if clean_id:
            return f"https://stackoverflow.com/users/{clean_id}"
        return "https://stackoverflow.com/"  # Invalid input fallback

    async def check(self, username: str, client, headers) -> ProviderResult:
        # This provider works best with a user ID, not a username.
        clean_id = "".join(filter(str.isdigit, username))
        ts = datetime.now(timezone.utc).isoformat()

        if not clean_id:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.NOT_FOUND,
                error="Invalid format. Stack Overflow requires a numeric user ID.",
                elapsed_ms=0,
                profile={},
                timestamp_iso=ts,
            )

        url = self.build_url(username)

        try:
            r = await client.get(
                url, timeout=self.timeout, follow_redirects=True, headers=headers
            )
            text = (r.text or "").lower()

            # Successful profiles have a clear title and reputation score
            if r.status_code == 200 and "reputation" in text and "profile" in text:
                status = ResultStatus.FOUND
            else:
                status = ResultStatus.NOT_FOUND

            return ProviderResult(
                provider=self.name,
                username=clean_id,
                url=str(r.url),  # Use the final URL after redirects
                status=status,
                http_status=r.status_code,
                evidence={"note": "Search by User ID"},
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
                profile={},
                timestamp_iso=ts,
            )


PROVIDERS = [StackOverflowProvider()]
