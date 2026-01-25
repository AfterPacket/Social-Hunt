from __future__ import annotations

from typing import List, Optional

import httpx

from social_hunt.addons_base import BaseAddon
from social_hunt.rate_limit import HostRateLimiter
from social_hunt.types import ProviderResult


class HelloAddon(BaseAddon):
    """A simple Hello World addon."""

    name = "hello_world"

    async def run(
        self,
        username: str,
        results: List[ProviderResult],
        client: httpx.AsyncClient,
        limiter: Optional[HostRateLimiter] = None,
    ) -> None:
        # Print to console to verify execution
        print(f"[HelloAddon] Processing results for {username}...")

        # Add a simple field to every result profile
        for r in results:
            if r.profile is None:
                r.profile = {}
            r.profile["hello_msg"] = "Hello from the plugin!"


ADDONS = [HelloAddon()]
