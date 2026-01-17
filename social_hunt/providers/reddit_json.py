from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict, Any

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class RedditAboutJSONProvider(BaseProvider):
    """Metadata-rich Reddit provider using /user/{username}/about.json.

    This endpoint is commonly used as a JSON view of user info, including created_utc,
    karma, and avatar fields (icon_img/snoovatar_img).
    """

    name = "reddit"
    timeout = 10
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        return f"https://www.reddit.com/user/{username}"

    async def check(self, username: str, client, headers: Dict[str, str]) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        api_url = f"https://www.reddit.com/user/{username}/about.json"

        try:
            # Reddit is picky about UA. Use a project UA string.
            api_headers = dict(headers)
            api_headers["User-Agent"] = "social-hunt/2.0 (OSINT research)"
            r = await client.get(api_url, timeout=self.timeout, follow_redirects=True, headers=api_headers)

            elapsed = int((time.monotonic() - start) * 1000)

            if r.status_code == 404:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.NOT_FOUND,
                    http_status=r.status_code,
                    elapsed_ms=elapsed,
                    evidence={"about_json": True},
                    profile={},
                    timestamp_iso=ts,
                )

            if r.status_code in (403, 429):
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.BLOCKED,
                    http_status=r.status_code,
                    elapsed_ms=elapsed,
                    evidence={"about_json": True},
                    profile={},
                    timestamp_iso=ts,
                )

            if r.status_code < 200 or r.status_code >= 300:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.UNKNOWN,
                    http_status=r.status_code,
                    elapsed_ms=elapsed,
                    evidence={"about_json": True},
                    profile={},
                    timestamp_iso=ts,
                )

            payload: Dict[str, Any] = r.json() if r.text else {}
            data = payload.get("data") or {}

            created_utc = data.get("created_utc")
            created_at = None
            if isinstance(created_utc, (int, float)):
                created_at = datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()

            profile = {
                "display_name": (data.get("subreddit") or {}).get("title") or username,
                "avatar_url": data.get("icon_img") or data.get("snoovatar_img"),
                "comment_karma": data.get("comment_karma"),
                "link_karma": data.get("link_karma"),
                "created_at": created_at,
            }

            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.FOUND,
                http_status=r.status_code,
                elapsed_ms=elapsed,
                evidence={"about_json": True},
                profile={k: v for k, v in profile.items() if v not in (None, "")},
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
                evidence={"about_json": True},
                profile={},
                error=str(e),
                timestamp_iso=ts,
            )


PROVIDERS = [RedditAboutJSONProvider()]
