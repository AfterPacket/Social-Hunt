from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

import httpx

from .providers_base import BaseProvider
from .rate_limit import HostRateLimiter
from .ua import UA_PROFILES, merge_headers
from .types import ProviderResult


class SocialHuntEngine:
    def __init__(
        self,
        registry: Dict[str, BaseProvider],
        max_concurrency: int = 6,
        min_host_interval_sec: float = 1.2,
    ):
        self.registry = registry
        self.max_concurrency = int(max_concurrency)
        self.limiter = HostRateLimiter(min_interval_sec=min_host_interval_sec)

    async def scan_username(self, username: str, providers: Optional[List[str]] = None) -> List[ProviderResult]:
        if providers:
            chosen = [p for p in providers if p in self.registry]
        else:
            chosen = list(self.registry.keys())

        sem = asyncio.Semaphore(self.max_concurrency)

        async with httpx.AsyncClient() as client:

            async def run_one(name: str) -> ProviderResult:
                prov = self.registry[name]
                url = prov.build_url(username)

                base_headers = UA_PROFILES.get("desktop_chrome", {})
                prof_headers = UA_PROFILES.get(getattr(prov, "ua_profile", "desktop_chrome"), {})
                headers = merge_headers(base_headers, prof_headers)

                await self.limiter.wait(url)

                async with sem:
                    return await prov.check(username, client, headers)

            tasks = [asyncio.create_task(run_one(p)) for p in chosen]
            results = await asyncio.gather(*tasks)

        return sorted(results, key=lambda r: r.provider.lower())
