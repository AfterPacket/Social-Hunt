from __future__ import annotations

import re
from typing import List, Set

import httpx

from ..addons_base import BaseAddon
from ..rate_limit import HostRateLimiter
from ..types import ProviderResult


_URL_RE = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)
# Loose domain match for plain text bios (no scheme)
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9-]{1,63}\.)+(?:[a-z]{2,63})\b", re.IGNORECASE
)
_HANDLE_RE = re.compile(r"(?<!\w)@([a-z0-9_\.]{2,30})", re.IGNORECASE)


def _dedupe(seq: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in seq:
        k = x.strip()
        if not k:
            continue
        if k.lower() in seen:
            continue
        seen.add(k.lower())
        out.append(k)
    return out


def _domain_of(url: str) -> str:
    try:
        u = httpx.URL(url)
        return (u.host or "").lower()
    except Exception:
        return ""


class BioLinksAddon(BaseAddon):
    """Extract URLs/domains/handles from public profile text."""

    name = "bio_links"

    async def run(
        self,
        username: str,
        results: List[ProviderResult],
        client: httpx.AsyncClient,
        limiter: HostRateLimiter | None = None,
    ) -> None:
        for r in results:
            prof = r.profile or {}
            text_parts = []
            for key in ("bio", "description"):
                v = prof.get(key)
                if isinstance(v, str) and v.strip():
                    text_parts.append(v.strip())

            if not text_parts:
                continue

            text = "\n".join(text_parts)

            urls = _dedupe(_URL_RE.findall(text))
            domains = []
            if urls:
                domains = [d for d in (_domain_of(u) for u in urls) if d]

            # Plain domains in bio (like example.com)
            plain_domains = _dedupe(_DOMAIN_RE.findall(text))
            # Avoid duplicating domains already captured from URLs
            plain_domains = [d for d in plain_domains if d.lower() not in {x.lower() for x in domains}]

            handles = _dedupe([m.group(1) for m in _HANDLE_RE.finditer(text)])

            if urls:
                prof["bio_urls"] = urls
            if domains:
                prof["bio_domains"] = _dedupe(domains)
            if plain_domains:
                prof["bio_domains"] = _dedupe((prof.get("bio_domains") or []) + plain_domains)
            if handles:
                prof["bio_handles"] = handles

            r.profile = prof


ADDONS = [BioLinksAddon()]
