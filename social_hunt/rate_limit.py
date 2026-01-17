from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from typing import Dict

class HostRateLimiter:
    """Simple minimum-interval-per-host limiter (polite pacing, not a bypass tool)."""

    def __init__(self, min_interval_sec: float = 1.2):
        self.min_interval_sec = float(min_interval_sec)
        self._locks: Dict[str, asyncio.Lock] = {}
        self._last: Dict[str, float] = {}

    async def wait(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if not host:
            return
        lock = self._locks.setdefault(host, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            delta = now - last
            if delta < self.min_interval_sec:
                await asyncio.sleep(self.min_interval_sec - delta)
            self._last[host] = time.monotonic()
