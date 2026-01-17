from __future__ import annotations

import hashlib
import io
from typing import List

import httpx
from PIL import Image

from ..addons_base import BaseAddon
from ..rate_limit import HostRateLimiter
from ..types import ProviderResult
from .net_safety import UnsafeURLError, safe_fetch_bytes


def _dhash(img: Image.Image, size: int = 8) -> str:
    """Compute a simple dHash (difference hash) as a 16-char hex string."""
    # Resize to (size+1, size) so we can compare adjacent pixels horizontally
    w, h = size + 1, size
    im = img.convert("L").resize((w, h), Image.Resampling.LANCZOS)
    px = list(im.getdata())

    bits = 0
    bitpos = 0
    for row in range(h):
        row_start = row * w
        for col in range(size):
            left = px[row_start + col]
            right = px[row_start + col + 1]
            if left > right:
                bits |= 1 << bitpos
            bitpos += 1

    # 64 bits -> 16 hex chars
    return f"{bits:016x}"


class AvatarFingerprintAddon(BaseAddon):
    """Download avatar URLs (safely) and compute sha256 + dHash fingerprints."""

    name = "avatar_fingerprint"

    def __init__(
        self,
        *,
        max_bytes: int = 2_000_000,
        timeout: float = 10.0,
    ) -> None:
        self.max_bytes = int(max_bytes)
        self.timeout = float(timeout)

    async def run(
        self,
        username: str,
        results: List[ProviderResult],
        client: httpx.AsyncClient,
        limiter: HostRateLimiter | None = None,
    ) -> None:
        for r in results:
            prof = r.profile or {}
            avatar_url = prof.get("avatar_url")
            if not isinstance(avatar_url, str) or not avatar_url.strip():
                continue

            # Skip if already fingerprinted
            if prof.get("avatar_sha256") and prof.get("avatar_dhash"):
                continue

            try:
                if limiter:
                    await limiter.wait(avatar_url)
                content, ctype = await safe_fetch_bytes(
                    client,
                    avatar_url,
                    timeout=self.timeout,
                    max_bytes=self.max_bytes,
                    accept_prefix="image",
                )

                sha = hashlib.sha256(content).hexdigest()
                img = Image.open(io.BytesIO(content))
                dh = _dhash(img)

                prof["avatar_sha256"] = sha
                prof["avatar_dhash"] = dh
                prof["avatar_bytes"] = len(content)
                if ctype:
                    prof["avatar_content_type"] = ctype

                r.profile = prof

            except (UnsafeURLError, httpx.HTTPError, OSError) as e:
                # Don't fail the whole scan: mark an avatar fetch error for this provider only.
                prof["avatar_fetch_error"] = str(e)
                r.profile = prof


ADDONS = [AvatarFingerprintAddon()]
