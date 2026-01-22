from __future__ import annotations

import re
from datetime import datetime, timezone

from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus


class DiscordProvider(BaseProvider):
    name = "discord"
    timeout = 10
    ua_profile = "desktop_chrome"

    def build_url(self, username: str) -> str:
        # Check if the username is a server invite code
        if re.match(r"^[a-zA-Z0-9]{2,10}$", username.strip()):
            return f"https://discord.gg/{username}"

        # Check if it's a numeric user ID
        if re.match(r"^\d{17,20}$", username.strip()):
            return f"https://discord.com/users/{username}"

        # Fallback for vanity URLs or other formats
        return f"https://discord.com/users/{username}"

    async def check(self, username: str, client, headers) -> ProviderResult:
        # --- IMPORTANT ---
        # Discord does not have public web profiles. You cannot reliably check if a
        # user exists via HTTP requests. A request to a valid or invalid user ID
        # will often return the same generic login page.
        # This provider serves as a link generator and format validator.

        url = self.build_url(username)
        ts = datetime.now(timezone.utc).isoformat()
        status = ResultStatus.UNKNOWN
        error = "Verification not possible. Discord profiles are not public."

        # Perform a basic format validation
        clean_user = username.strip()
        is_id = re.match(r"^\d{17,20}$", clean_user)
        is_invite = not is_id and re.match(r"^[a-zA-Z0-9]{2,10}$", clean_user)

        if not (is_id or is_invite):
            # If it's not a standard ID or invite code, it's likely an invalid format
            status = ResultStatus.NOT_FOUND
            error = "Invalid Discord ID or invite code format."

        # In a real check, we would perform an HTTP request here.
        # But for Discord, it is omitted as it provides no value.
        # We return a pre-defined result instead.

        return ProviderResult(
            provider=self.name,
            username=username,
            url=url,
            status=status,
            http_status=None,
            elapsed_ms=0,
            evidence={
                "note": "Link generation only.",
                "type": "User ID" if is_id else ("Invite" if is_invite else "Unknown"),
            },
            profile={},
            error=error,
            timestamp_iso=ts,
        )


PROVIDERS = [DiscordProvider()]
