from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Dict

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class GitHubAPIProvider(BaseProvider):
    """Metadata-rich GitHub provider using the public GitHub REST API.

    This uses GET https://api.github.com/users/{username}, which (for public profiles)
    returns fields like avatar_url, followers, following, created_at, bio, etc.
    """

    name = "github"
    timeout = 10
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        return f"https://github.com/{username}"

    async def check(self, username: str, client, headers: Dict[str, str]) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()
        api_url = f"https://api.github.com/users/{username}"

        try:
            api_headers = dict(headers)
            api_headers.setdefault("Accept", "application/vnd.github+json")
            r = await client.get(api_url, timeout=self.timeout, follow_redirects=True, headers=api_headers)

            elapsed = int((time.monotonic() - start) * 1000)

            # GitHub uses 404 for non-existent users; 200 for existing.
            if r.status_code == 404:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.NOT_FOUND,
                    http_status=r.status_code,
                    elapsed_ms=elapsed,
                    evidence={"api": True},
                    profile={},
                    timestamp_iso=ts,
                )

            if r.status_code == 403:
                # Could be rate limit or access policy
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.BLOCKED,
                    http_status=r.status_code,
                    elapsed_ms=elapsed,
                    evidence={"api": True},
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
                    evidence={"api": True},
                    profile={},
                    timestamp_iso=ts,
                )

            data = r.json() if r.text else {}
            profile = {
                "display_name": data.get("name") or data.get("login"),
                "avatar_url": data.get("avatar_url"),
                "followers": data.get("followers"),
                "following": data.get("following"),
                "created_at": data.get("created_at"),
                "bio": data.get("bio"),
                "location": data.get("location"),
                "blog": data.get("blog"),
            }

            # If the API succeeds, treat as FOUND.
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.FOUND,
                http_status=r.status_code,
                elapsed_ms=elapsed,
                evidence={"api": True},
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
                evidence={"api": True},
                profile={},
                error=str(e),
                timestamp_iso=ts,
            )


PROVIDERS = [GitHubAPIProvider()]
