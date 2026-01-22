from __future__ import annotations

import re
from datetime import datetime, timezone

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class GoodreadsProvider(BaseProvider):
    name = "goodreads"
    timeout = 10
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        # Goodreads URL format is /user/show/{id}-{username}
        # A simple username search is not directly supported via a clean URL.
        # This plugin will search for the user and try to find their profile.
        return f"https://www.goodreads.com/search?q={username}"

    async def check(self, username: str, client, headers) -> ProviderResult:
        search_url = self.build_url(username)
        ts = datetime.now(timezone.utc).isoformat()

        try:
            r = await client.get(
                search_url, timeout=self.timeout, follow_redirects=True, headers=headers
            )
            text = (r.text or "").lower()

            # Find the first user profile link in the search results
            # e.g., <a class="userProfileLink" href="/user/show/12345-username">
            match = re.search(r'href="(/user/show/[^"]+)"', text)

            if match:
                profile_url = f"https://www.goodreads.com{match.group(1)}"
                status = ResultStatus.FOUND
                # Optionally, you could make a second request to the profile_url
                # to get more details, but finding the link is good evidence.
            else:
                profile_url = search_url
                status = ResultStatus.NOT_FOUND

            return ProviderResult(
                provider=self.name,
                username=username,
                url=profile_url,
                status=status,
                http_status=r.status_code,
                evidence={"note": "Found via user search"},
                profile={},
                timestamp_iso=ts,
            )
        except Exception as e:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=search_url,
                status=ResultStatus.ERROR,
                error=str(e),
                profile={},
                timestamp_iso=ts,
            )


PROVIDERS = [GoodreadsProvider()]
