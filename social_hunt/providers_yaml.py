from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import List, Dict, Any

from .types import ProviderResult, ResultStatus
from .providers_base import BaseProvider
from .metadata import extract_opengraph, extract_json_ld, extract_counts_from_text

BLOCK_HINTS = [
    "captcha",
    "verify you are human",
    "unusual traffic",
    "access denied",
    "temporarily blocked",
    "cloudflare",
    "security check",
    "please enable cookies",
]

class PatternProvider(BaseProvider):
    def __init__(self, name: str, cfg: Dict[str, Any]):
        self.name = name
        self._url_tpl = str(cfg["url"])
        self.timeout = int(cfg.get("timeout", 10))
        self.ua_profile = str(cfg.get("ua_profile", "desktop_chrome"))
        self.success_patterns: List[str] = list(cfg.get("success_patterns", []))
        self.error_patterns: List[str] = list(cfg.get("error_patterns", []))
        self.note = cfg.get("note")

    def build_url(self, username: str) -> str:
        return self._url_tpl.replace("{username}", username)

    def _classify(self, content_lower: str, success_patterns: List[str], error_patterns: List[str]) -> ResultStatus:
        if any(h in content_lower for h in BLOCK_HINTS):
            return ResultStatus.BLOCKED
        if any(p.lower() in content_lower for p in error_patterns):
            return ResultStatus.NOT_FOUND
        if any(p.lower() in content_lower for p in success_patterns):
            return ResultStatus.FOUND
        return ResultStatus.UNKNOWN

    async def check(self, username: str, client, headers: Dict[str, str]) -> ProviderResult:
        url = self.build_url(username)
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()

        try:
            resp = await client.get(url, timeout=self.timeout, follow_redirects=True, headers=headers)
            raw_html = resp.text or ""
            text = raw_html.lower()

            # Substitute {username} in YAML patterns at runtime (without mutating provider)
            success_patterns = [p.replace("{username}", username) for p in self.success_patterns]
            error_patterns = [p.replace("{username}", username) for p in self.error_patterns]

            status = self._classify(text, success_patterns=success_patterns, error_patterns=error_patterns)

            # small platform hints
            if self.name == "tiktok" and f"@{username.lower()}" in text:
                status = ResultStatus.FOUND
            if self.name == "github" and f"users/{username.lower()}" in text:
                status = ResultStatus.FOUND

            elapsed = int((time.monotonic() - start) * 1000)
            # Metadata extraction is best-effort and should never change FOUND/NOT_FOUND decisions.
            profile: Dict[str, Any] = {}
            try:
                profile.update(extract_opengraph(raw_html))
                # JSON-LD can fill gaps if OG tags are missing.
                for k, v in extract_json_ld(raw_html).items():
                    profile.setdefault(k, v)
                # Extremely conservative count sniffing (may be absent for many platforms).
                profile.update(extract_counts_from_text(text))
            except Exception:
                # swallow parsing errors
                pass

            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=status,
                http_status=resp.status_code,
                elapsed_ms=elapsed,
                evidence={"len": len(text)},
                profile=profile,
                timestamp_iso=ts,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return ProviderResult(
                provider=self.name,
                username=username,
                url=url,
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=elapsed,
                evidence={},
                profile={},
                error=str(e),
                timestamp_iso=ts,
            )
