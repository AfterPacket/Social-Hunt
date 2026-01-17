from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

from .rate_limit import HostRateLimiter
from .types import ProviderResult


class BaseAddon(ABC):
    """Post-processing enrichment that runs after provider checks.

    Addons MUST be safe-by-default:
    - only enrich data already discovered by providers
    - do not attempt real-identity resolution
    - enforce network safety limits (SSRF/size/timeouts) if they fetch URLs
    """

    name: str = ""

    @abstractmethod
    async def run(
        self,
        username: str,
        results: List[ProviderResult],
        client: httpx.AsyncClient,
        limiter: Optional[HostRateLimiter] = None,
    ) -> None:
        """Mutate results in-place."""
