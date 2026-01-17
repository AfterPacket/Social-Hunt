from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup


_KM_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)\s*([KM])$")
_INT_RE = re.compile(r"^[0-9][0-9,]*$")


def parse_human_int(s: str) -> Optional[int]:
    """Parse humanized counts like '1,234', '12.3K', '4M' into int."""
    if not s:
        return None
    t = s.strip().upper().replace(" ", "")

    m = _KM_RE.match(t)
    if m:
        base = float(m.group(1))
        mult = 1000 if m.group(2) == "K" else 1000000
        return int(base * mult)

    # plain integer with commas
    if _INT_RE.match(t):
        try:
            return int(t.replace(",", ""))
        except ValueError:
            return None

    # fallback: grab first integer-ish
    m2 = re.search(r"([0-9][0-9,]*)(?!\d)", t)
    if m2:
        try:
            return int(m2.group(1).replace(",", ""))
        except ValueError:
            return None

    return None


def extract_opengraph(html: str) -> Dict[str, Any]:
    """Extract common metadata (title/description/image/url) from OG + Twitter cards."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")

    def meta(prop: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return str(tag.get("content")).strip()
        tag = soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            return str(tag.get("content")).strip()
        return None

    title = meta("og:title") or meta("twitter:title")
    desc = meta("og:description") or meta("twitter:description")
    img = meta("og:image") or meta("twitter:image")
    url = meta("og:url")

    # fall back to <title>
    if not title:
        t = soup.find("title")
        if t and t.text:
            title = t.text.strip()

    out: Dict[str, Any] = {}
    if title:
        out["display_name"] = title
    if desc:
        out["description"] = desc
    if img:
        out["avatar_url"] = img
    if url:
        out["canonical_url"] = url

    return out


def extract_json_ld(html: str) -> Dict[str, Any]:
    """Extract a few useful fields from JSON-LD blocks if present."""
    if not html:
        return {}
    soup = BeautifulSoup(html, "html.parser")
    blocks = soup.find_all("script", attrs={"type": "application/ld+json"})
    if not blocks:
        return {}

    def coerce_image(v: Any) -> Optional[str]:
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            # ImageObject
            return v.get("url") or v.get("contentUrl")
        if isinstance(v, list) and v:
            return coerce_image(v[0])
        return None

    for b in blocks:
        txt = (b.string or "").strip()
        if not txt:
            continue
        try:
            data = json.loads(txt)
        except Exception:
            continue

        # sometimes a list of things
        candidates = data if isinstance(data, list) else [data]

        for c in candidates:
            if not isinstance(c, dict):
                continue

            out: Dict[str, Any] = {}
            name = c.get("name")
            if isinstance(name, str) and name.strip():
                out["display_name"] = name.strip()

            image = coerce_image(c.get("image"))
            if image:
                out["avatar_url"] = image

            url = c.get("url")
            if isinstance(url, str) and url.strip():
                out["canonical_url"] = url.strip()

            if out:
                return out

    return {}


def extract_counts_from_text(text_lower: str) -> Dict[str, Any]:
    """Best-effort parse follower/following/subscriber counts from page text."""
    if not text_lower:
        return {}

    # Keep this conservative; many pages mention these words unrelated to counts.
    patterns: List[tuple[str, str]] = [
        (r"([0-9][0-9,\.]*\s*[KM]?)\s+followers\b", "followers"),
        (r"([0-9][0-9,\.]*\s*[KM]?)\s+following\b", "following"),
        (r"([0-9][0-9,\.]*\s*[KM]?)\s+subscribers\b", "subscribers"),
        (r"([0-9][0-9,\.]*\s*[KM]?)\s+members\b", "members"),
    ]

    out: Dict[str, Any] = {}
    for pat, key in patterns:
        m = re.search(pat, text_lower)
        if m:
            val = parse_human_int(m.group(1))
            if val is not None:
                out[key] = val

    return out
