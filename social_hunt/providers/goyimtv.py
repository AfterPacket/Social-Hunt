from __future__ import annotations

import asyncio
import time
import urllib.parse
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class GoyimTVProvider(BaseProvider):
    name = "goyimtv"
    timeout = 25
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        # tf=6 appears to be a filter for Channels/Users
        q = urllib.parse.quote_plus(username)
        return f"https://goyimtv.st/search?tf=6&q={q}"

    async def check(self, username: str, client, headers) -> ProviderResult:
        url = self.build_url(username)
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()

        # GoyimTV may employ basic anti-bot protections (DDoS-Guard / PoW).
        # We attempt to bypass simple checks by mimicking a full browser request
        # and implementing a retry strategy.

        # Ensure we have robust headers
        headers["Accept"] = (
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        )
        headers["Accept-Language"] = "en-US,en;q=0.5"
        headers["Referer"] = "https://goyimtv.st/"
        headers["Upgrade-Insecure-Requests"] = "1"
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "same-origin"
        headers["Sec-Fetch-User"] = "?1"

        try:
            r = await client.get(
                url, timeout=self.timeout, follow_redirects=True, headers=headers
            )

            # Basic retry logic for soft-blocks (503/403 often used by protection layers)
            if r.status_code in [403, 503, 429]:
                # Wait a moment for potential "checking your browser" screens to pass (if using a session, though client is stateless)
                # Just retrying might pass if it's a leaky bucket rate limit or temporary error.
                await asyncio.sleep(2.0)
                r = await client.get(
                    url, timeout=self.timeout, follow_redirects=True, headers=headers
                )

            text = (r.text or "").lower()
            soup = BeautifulSoup(r.text, "html.parser")

            status = ResultStatus.UNKNOWN
            profile = {}

            # Check for common "Not Found" indicators in search results
            not_found_indicators = [
                "no results found",
                "nothing found",
                "search returned no results",
            ]

            if any(x in text for x in not_found_indicators):
                status = ResultStatus.NOT_FOUND
            else:
                # Analyze search results for a matching channel
                # We look for links that look like /channel/Username or /channel/ID
                # Since we want to verify the specific username, we look for text or href matches.

                found_match = False

                # GoyimTV search results usually display channels with the username in the title or link
                links = soup.find_all("a", href=True)
                for link in links:
                    href = link["href"].lower()
                    link_text = link.get_text().strip().lower()

                    # Strict check: Does the username appear in a channel link?
                    # Example: https://goyimtv.st/channel/239482394 (ID based) or /channel/Name

                    # If the link is to a channel AND the visible text matches the username
                    if "/channel/" in href and username.lower() == link_text:
                        found_match = True
                        break

                    # Also check if the username is part of the href itself (if they support vanity URLs)
                    if f"/channel/{username.lower()}" in href:
                        found_match = True
                        break

                if found_match:
                    status = ResultStatus.FOUND
                    if soup.title:
                        profile["page_title"] = soup.title.string.strip()
                else:
                    # If we got a 200 OK but no specific match for the username, it's likely not there.
                    # However, if the page is just the homepage (redirected), treat as unknown/not_found.
                    if "welcome to goyimtv" in text and "search" not in r.url.path:
                        status = ResultStatus.NOT_FOUND
                    elif len(links) < 5:
                        # Very few links usually means empty result set even if text didn't trigger
                        status = ResultStatus.NOT_FOUND
                    else:
                        # Ambiguous - maybe we found partial matches?
                        # Safe to say NOT_FOUND if strict matching failed.
                        status = ResultStatus.NOT_FOUND

            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=status,
                http_status=r.status_code,
                elapsed_ms=int((time.monotonic() - start) * 1000),
                evidence={
                    "len": len(text),
                    "title": soup.title.string if soup.title else None,
                },
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
                elapsed_ms=int((time.monotonic() - start) * 1000),
                profile={},
                timestamp_iso=ts,
            )


PROVIDERS = [GoyimTVProvider()]
