from __future__ import annotations

import asyncio
import os
from contextlib import AsyncExitStack
from typing import Callable, Dict, List, Optional

import httpx

from .addons_base import BaseAddon
from .addons_registry import build_addon_registry, load_enabled_addons
from .providers_base import BaseProvider
from .rate_limit import HostRateLimiter
from .types import ProviderResult, ResultStatus
from .ua import UA_PROFILES, merge_headers


def _is_onion_url(url: str) -> bool:
    """Return True only when the URL hostname is an onion service."""
    try:
        host = (httpx.URL(url).host or "").rstrip(".").lower()
    except Exception:
        return False
    return host == ".onion" or host.endswith(".onion")


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
        self.addon_registry = build_addon_registry()
        self.enabled_addon_names = load_enabled_addons()

    async def scan_username(
        self,
        username: str,
        providers: Optional[List[str]] = None,
        dynamic_addons: Optional[List[BaseAddon]] = None,
        progress_callback: Optional[Callable[[ProviderResult], None]] = None,
    ) -> List[ProviderResult]:
        if providers:
            chosen = [p for p in providers if p in self.registry]
        else:
            chosen = list(self.registry.keys())

        sem = asyncio.Semaphore(self.max_concurrency)

        # SOCIAL_HUNT_PROXY      — Tor/darkweb proxy, used exclusively for .onion URLs
        #                          e.g. socks5h://127.0.0.1:9050
        # SOCIAL_HUNT_CLEARNET_PROXY — optional residential/HTTP proxy for clearnet
        #                              providers that set use_proxy=True (e.g. BreachVIP)
        #                          e.g. http://user:pass@proxy.example.com:8080
        tor_proxy_url = (
            os.getenv("SOCIAL_HUNT_PROXY")
            or os.getenv("SOCIAL_HUNT_TOR_PROXY")
            or "socks5://127.0.0.1:9050"
        )
        clearnet_proxy_url = os.getenv("SOCIAL_HUNT_CLEARNET_PROXY")

        async with AsyncExitStack() as stack:
            # Default direct client
            client_direct = await stack.enter_async_context(
                httpx.AsyncClient(trust_env=False)
            )

            # Tor client — .onion URLs only
            client_tor = None
            if tor_proxy_url:
                client_tor = await stack.enter_async_context(
                    httpx.AsyncClient(proxy=tor_proxy_url, trust_env=False)
                )

            # Clearnet proxy client — for providers that opt in via use_proxy=True
            client_clearnet_proxy = None
            if clearnet_proxy_url:
                client_clearnet_proxy = await stack.enter_async_context(
                    httpx.AsyncClient(proxy=clearnet_proxy_url, trust_env=False)
                )

            async def run_one(name: str) -> ProviderResult:
                prov = self.registry[name]
                url = prov.build_url(username)
                is_onion = _is_onion_url(url)

                base_headers = UA_PROFILES.get("desktop_chrome", {})
                prof_headers = UA_PROFILES.get(
                    getattr(prov, "ua_profile", "desktop_chrome"), {}
                )
                headers = merge_headers(base_headers, prof_headers)

                await self.limiter.wait(url)

                # Client selection:
                #   .onion URLs → Tor proxy (SOCIAL_HUNT_PROXY)
                #   use_proxy providers → clearnet proxy (SOCIAL_HUNT_CLEARNET_PROXY)
                #   fallback → direct
                if is_onion and client_tor:
                    use_client = client_tor
                elif is_onion:
                    from datetime import datetime, timezone

                    res = ProviderResult(
                        provider=prov.name,
                        username=username,
                        url=url,
                        status=ResultStatus.ERROR,
                        http_status=None,
                        elapsed_ms=0,
                        evidence={},
                        profile={},
                        error=(
                            "Tor is required for this .onion provider, but the Tor "
                            "proxy could not be initialized. Start Tor or set "
                            "SOCIAL_HUNT_PROXY."
                        ),
                        timestamp_iso=datetime.now(timezone.utc).isoformat(),
                    )
                    if progress_callback:
                        progress_callback(res)
                    return res
                elif getattr(prov, "use_proxy", False) and client_clearnet_proxy:
                    use_client = client_clearnet_proxy
                else:
                    use_client = client_direct

                async with sem:
                    provider_timeout = getattr(prov, "timeout", 15) + 5
                    try:
                        res = await asyncio.wait_for(
                            prov.check(username, use_client, headers),
                            timeout=provider_timeout,
                        )
                        if is_onion and res.status == ResultStatus.ERROR and res.error:
                            low_error = res.error.lower()
                            if any(
                                marker in low_error
                                for marker in (
                                    "all connection attempts failed",
                                    "connection refused",
                                    "connecterror",
                                    "socks",
                                )
                            ):
                                res.error = (
                                    "Tor proxy is unavailable at "
                                    f"{tor_proxy_url}. Start Tor or verify the "
                                    "SOCIAL_HUNT_PROXY setting."
                                )
                    except asyncio.TimeoutError:
                        from datetime import datetime, timezone
                        res = ProviderResult(
                            provider=prov.name,
                            username=username,
                            url=prov.build_url(username),
                            status=ResultStatus.ERROR,
                            http_status=None,
                            elapsed_ms=provider_timeout * 1000,
                            evidence={},
                            profile={},
                            error=f"Timed out after {provider_timeout}s",
                            timestamp_iso=datetime.now(timezone.utc).isoformat(),
                        )

                    # Demo mode censorship
                    from .demo import censor_value, is_demo_mode

                    if is_demo_mode():
                        if res.profile:
                            censored_prof = {}
                            for k, v in res.profile.items():
                                if k == "raw_results" and isinstance(v, list):
                                    from .demo import censor_breach_data

                                    censored_prof[k] = censor_breach_data(v)
                                elif isinstance(v, dict):
                                    censored_prof[k] = {
                                        ik: censor_value(iv, ik) for ik, iv in v.items()
                                    }
                                else:
                                    censored_prof[k] = censor_value(v, k)
                            res.profile = censored_prof

                        if res.evidence:
                            censored_ev = {}
                            for k, v in res.evidence.items():
                                if isinstance(v, dict):
                                    censored_ev[k] = {
                                        ik: censor_value(iv, ik) for ik, iv in v.items()
                                    }
                                else:
                                    censored_ev[k] = censor_value(v, k)
                            res.evidence = censored_ev

                    if progress_callback:
                        progress_callback(res)
                    return res

            tasks = [asyncio.create_task(run_one(p)) for p in chosen]
            results = await asyncio.gather(*tasks)

            # --- Addon Processing ---
            addons_to_run = [
                self.addon_registry[name]
                for name in self.enabled_addon_names
                if name in self.addon_registry
            ]
            if dynamic_addons:
                addons_to_run.extend(dynamic_addons)

            if addons_to_run:
                addon_tasks = [
                    asyncio.create_task(
                        addon.run(username, results, client_direct, self.limiter)
                    )
                    for addon in addons_to_run
                ]
                await asyncio.gather(*addon_tasks)

        return sorted(results, key=lambda r: r.provider.lower())
