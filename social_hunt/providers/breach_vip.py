from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

import httpx

from ..demo import censor_breach_data, is_demo_mode
from ..providers_base import BaseProvider
from ..types import ProviderResult, ResultStatus

# Import settings store for proxy configuration
try:
    from api.settings_store import SettingsStore

    SETTINGS_AVAILABLE = True
except ImportError:
    SettingsStore = None
    SETTINGS_AVAILABLE = False


class BreachVIPProvider(BaseProvider):
    """BreachVIP breach data search provider with proxy support.

    Searches for data across multiple fields in the BreachVIP database.
    Supports configurable proxy settings with failover strategies.

    Input:
      - Username/Email/Phone/DiscordID/etc: searches across relevant fields

    Rate limit: 15 requests per minute
    Maximum results: 10,000 per search

    No API key or settings required.
    Requests are always made directly (no proxy, trust_env=False) so that
    system-level HTTP_PROXY / HTTPS_PROXY env vars and the optional Tor
    SOCKS proxy (SOCIAL_HUNT_PROXY) are never applied to breach.vip calls.
    """

    name = "breachvip"
    timeout = 15
    ua_profile = "desktop_chrome"

    def __init__(self):
        super().__init__()
        # Load proxy configuration from settings or environment
        self._load_proxy_settings()

    def _is_valid_proxy_url(self, url):
        """Validate if a proxy URL is properly formatted."""
        if not url or not isinstance(url, str):
            return False

        url = url.strip()
        if not url:
            return False

        # Check for supported proxy schemes
        supported_schemes = ["http://", "https://", "socks5://", "socks4://"]
        if not any(url.lower().startswith(scheme) for scheme in supported_schemes):
            return False

        # Basic format validation - must have host:port after scheme
        try:
            # Remove scheme to check host:port format
            for scheme in supported_schemes:
                if url.lower().startswith(scheme):
                    remaining = url[len(scheme) :]
                    # Must have at least host:port format (minimum: "a:1")
                    if ":" not in remaining or len(remaining) < 3:
                        return False
                    break
            return True
        except Exception:
            return False

    def _load_proxy_settings(self):
        """Load proxy settings from UI settings or environment variables (fallback)."""
        # Initialize defaults
        self.proxy_enabled = False
        self.proxy_url = None
        self.proxy_auth = None
        self.proxy_strategy = (
            "regular_first"  # "regular_first", "proxy_first", "proxy_only"
        )
        self.use_residential_ip = False

        # Load from environment variables first (fallback)
        env_proxy_enabled = (
            os.getenv("BREACHVIP_PROXY_ENABLED", "false").lower() == "true"
        )
        env_proxy_url = os.getenv("BREACHVIP_PROXY_URL")
        env_proxy_auth = os.getenv("BREACHVIP_PROXY_AUTH")
        env_proxy_strategy = os.getenv("BREACHVIP_PROXY_STRATEGY", "regular_first")
        env_residential = (
            os.getenv("BREACHVIP_USE_RESIDENTIAL_IP", "false").lower() == "true"
        )

        # Apply environment variable settings (with URL validation)
        if env_proxy_enabled or (
            env_proxy_url and self._is_valid_proxy_url(env_proxy_url)
        ):
            self.proxy_enabled = True
        if env_proxy_url and self._is_valid_proxy_url(env_proxy_url):
            self.proxy_url = env_proxy_url
        if env_proxy_auth:
            self.proxy_auth = env_proxy_auth
        if env_proxy_strategy in ["regular_first", "proxy_first", "proxy_only"]:
            self.proxy_strategy = env_proxy_strategy
        self.use_residential_ip = env_residential

        # Load from settings if available (overrides environment)
        if SETTINGS_AVAILABLE and SettingsStore is not None:
            try:
                settings_path = os.getenv(
                    "SOCIAL_HUNT_SETTINGS_PATH", "data/settings.json"
                )
                settings_store = SettingsStore(settings_path)
                settings = settings_store.load()

                # Get BreachVIP specific settings using dot notation
                def get_setting_value(key, default=None):
                    """Extract value from settings, handling both direct values and dict format."""
                    full_key = f"breachvip.{key}"
                    val = settings.get(full_key, default)
                    if isinstance(val, dict) and "value" in val:
                        return val["value"]
                    return val

                # Load proxy settings from UI (only override env vars if explicitly set)
                proxy_enabled = get_setting_value("proxy_enabled")
                if proxy_enabled is not None:
                    self.proxy_enabled = bool(proxy_enabled)

                # Only override URL if web setting has a valid value
                proxy_url = get_setting_value("proxy_url")
                if proxy_url:
                    url_str = str(proxy_url).strip()
                    if url_str and self._is_valid_proxy_url(url_str):
                        self.proxy_url = url_str

                # Only override auth if web setting has a value
                proxy_auth = get_setting_value("proxy_auth")
                if proxy_auth and str(proxy_auth).strip():
                    self.proxy_auth = str(proxy_auth).strip()

                # Only override strategy if web setting is set (don't use default)
                strategy = get_setting_value("proxy_strategy")
                if strategy and strategy in [
                    "regular_first",
                    "proxy_first",
                    "proxy_only",
                ]:
                    self.proxy_strategy = strategy

                # Only override residential setting if explicitly set
                residential = get_setting_value("use_residential_ip")
                if residential is not None:
                    self.use_residential_ip = bool(residential)

            except Exception as e:
                print(f"[DEBUG] BreachVIP: Could not load settings: {e}")
                # Fall back to environment variables or defaults

        if self.proxy_enabled and self.proxy_url:
            print(
                f"[DEBUG] BreachVIP proxy config: ENABLED, strategy={self.proxy_strategy}, url={self.proxy_url}"
            )
        else:
            print(
                f"[DEBUG] BreachVIP proxy config: DISABLED - using direct VPS connection"
            )

    def _get_connection_strategies(self):
        """Get ordered list of connection strategies to try."""
        strategies = []

        # Build proxy config if available
        proxy_config = {}
        if self.proxy_enabled and self.proxy_url:
            proxy_config["proxies"] = self.proxy_url
            if self.proxy_auth and ":" in self.proxy_auth:
                proxy_config["proxy_auth"] = tuple(self.proxy_auth.split(":", 1))

        # Determine strategy order
        if self.proxy_strategy == "proxy_only":
            if proxy_config:
                strategies.append(("proxy", proxy_config))
            else:
                print(
                    "[WARNING] BreachVIP: proxy_only strategy but no proxy configured, falling back to direct VPS connection"
                )
                strategies.append(("direct_vps", {}))
        elif self.proxy_strategy == "proxy_first":
            if proxy_config:
                strategies.append(("proxy", proxy_config))
            strategies.append(("direct_vps", {}))
        else:  # "regular_first" or default
            strategies.append(("direct_vps", {}))
            if proxy_config:
                strategies.append(("proxy", proxy_config))

        return strategies

    def build_url(self, username: str) -> str:
        return "https://breach.vip/api/search"

    def _determine_search_fields(self, search_term: str) -> List[str]:
        """Determine which fields to search based on the input format."""
        search_term = search_term.lower().strip()

        # Default fields to search
        fields = ["email", "username", "name"]

        # Add specific fields based on input format
        if "@" in search_term:
            # Email format - prioritize email field
            fields = ["email", "username", "name"]
        elif search_term.isdigit():
            # Numeric - could be phone, user ID, etc.
            fields = ["phone", "userid", "username", "email"]
        elif len(search_term) == 18 and search_term.isdigit():
            # Discord ID format
            fields = ["discordid", "userid", "username", "email"]
        elif search_term.startswith("+") or (
            search_term.replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
            .isdigit()
        ):
            # Phone number format
            fields = ["phone", "username", "email"]

        return fields

    async def check(
        self, username: str, client, headers: Dict[str, str]
    ) -> ProviderResult:
        start = time.monotonic()
        ts = datetime.now(timezone.utc).isoformat()

        search_term = (username or "").strip()
        if not search_term:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=0,
                evidence={"breachvip": True},
                profile={},
                error="empty input",
                timestamp_iso=ts,
            )

        # Prepare enhanced headers to better mimic a real browser/AJAX request
        breachvip_headers = dict(headers)
        breachvip_headers.update(
            {
                "Accept": "application/json, text/plain, */*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Content-Type": "application/json",
                "DNT": "1",
                "Host": "breach.vip",
                "Origin": "https://breach.vip",
                "Pragma": "no-cache",
                "Referer": "https://breach.vip/",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "X-Requested-With": "XMLHttpRequest",
            }
        )

        # Determine search fields and prepare request
        fields_to_search = self._determine_search_fields(search_term)
        is_wildcard = "*" in search_term

        request_body = {
            "term": search_term,
            "fields": fields_to_search,
            "categories": [],
            "wildcard": is_wildcard,
            "case_sensitive": False,
        }

        profile: Dict[str, Any] = {
            "account": search_term,
            "fields_searched": fields_to_search,
        }
        evidence: Dict[str, Any] = {"breachvip": True}

        # Always use a dedicated direct client — trust_env=False ensures that
        # HTTP_PROXY / HTTPS_PROXY env vars and any SOCKS proxy configured via
        # SOCIAL_HUNT_PROXY are never applied to breach.vip requests.
        try:
            async with httpx.AsyncClient(trust_env=False) as direct_client:
                response = await direct_client.post(
                    self.build_url(username),
                    timeout=self.timeout,
                    headers=breachvip_headers,
                    json=request_body,
                )

        # Retry logic with connection strategy failover
        max_retries = 3
        retry_delays = [2, 5, 10]  # seconds

        last_error = None
        response = None

        for attempt in range(max_retries):
            for strategy_name, proxy_config in connection_strategies:
                try:
                    if proxy_config:
                        print(
                            f"[DEBUG] BreachVIP attempt {attempt + 1}: using {strategy_name} via {proxy_config.get('proxies')}"
                        )
                    else:
                        print(
                            f"[DEBUG] BreachVIP attempt {attempt + 1}: using {strategy_name} (direct VPS IP)"
                        )

                    response = await client.post(
                        self.build_url(username),
                        timeout=self.timeout,
                        headers=breachvip_headers,
                        json=request_body,
                        **proxy_config,
                    )

                    elapsed = int((time.monotonic() - start) * 1000)

                    if response.status_code == 200:
                        connection_type = (
                            f"via {proxy_config.get('proxies')}"
                            if proxy_config
                            else "direct VPS"
                        )
                        print(
                            f"[SUCCESS] BreachVIP {strategy_name} succeeded ({connection_type})"
                        )
                        break  # Success, exit strategy loop
                    else:
                        connection_type = (
                            f"via {proxy_config.get('proxies')}"
                            if proxy_config
                            else "direct VPS"
                        )
                        print(
                            f"[ERROR] BreachVIP {strategy_name} ({connection_type}) returned {response.status_code}: {response.text[:200]}"
                        )
                        last_error = f"HTTP {response.status_code}"
                        # Try next strategy
                        continue

                except Exception as e:
                    connection_type = (
                        f"via {proxy_config.get('proxies')}"
                        if proxy_config
                        else "direct VPS"
                    )
                    print(
                        f"[ERROR] BreachVIP {strategy_name} ({connection_type}) connection failed: {e}"
                    )
                    last_error = str(e)
                    # Try next strategy
                    continue

            # If we have a successful response, break out of retry loop
            if response and response.status_code == 200:
                break

            # If not the last attempt, wait and retry all strategies
            if attempt < max_retries - 1:
                delay = retry_delays[attempt]
                print(f"[RETRY] BreachVIP retrying all strategies in {delay}s...")
                await asyncio.sleep(delay)

        # Handle final result
        if not response:
            elapsed = int((time.monotonic() - start) * 1000)
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.ERROR,
                http_status=None,
                elapsed_ms=elapsed,
                evidence=evidence,
                profile=profile,
                error=f"Connection failed: {last_error}",
                timestamp_iso=ts,
            )

        elapsed = int((time.monotonic() - start) * 1000)

        if response.status_code != 200:
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.ERROR,
                http_status=response.status_code,
                elapsed_ms=elapsed,
                evidence=evidence,
                profile=profile,
                error=f"API returned {response.status_code}",
                timestamp_iso=ts,
            )

        # Process successful response
        try:
            raw_json = response.json() if response.text else []
            data = []

            # Handle different API response shapes
            if isinstance(raw_json, dict):
                if "results" in raw_json and isinstance(raw_json["results"], list):
                    data = raw_json["results"]
                elif "data" in raw_json and isinstance(raw_json["data"], list):
                    data = raw_json["data"]
                else:
                    data = [raw_json]
            elif isinstance(raw_json, list):
                data = raw_json

            # Further refine flattening
            if len(data) == 1 and isinstance(data[0], dict):
                nested = data[0]
                if "results" in nested and isinstance(nested["results"], list):
                    data = nested["results"]
                elif "data" in nested and isinstance(nested["data"], list):
                    data = nested["data"]

            print(f"[DEBUG] BreachVIP found {len(data)} records")

            # Process records
            if not data:
                return ProviderResult(
                    provider=self.name,
                    username=username,
                    url=self.build_url(username),
                    status=ResultStatus.NOT_FOUND,
                    http_status=response.status_code,
                    elapsed_ms=elapsed,
                    evidence=evidence,
                    profile=profile,
                    timestamp_iso=ts,
                )

            # Apply demo mode filtering if enabled
            if is_demo_mode():
                data = censor_breach_data(data)

            # Build result profile with breach data
            breach_sources = set()
            breach_count = len(data)
            sample_fields = set()

            for record in data[:5]:  # Sample first 5 records for metadata
                if isinstance(record, dict):
                    # Extract source/breach information
                    source = (
                        record.get("source")
                        or record.get("breach")
                        or record.get("database")
                    )
                    if source:
                        breach_sources.add(str(source))

                    # Track available fields
                    sample_fields.update(record.keys())

            profile.update(
                {
                    "breach_count": breach_count,
                    "breach_sources": list(breach_sources),
                    "available_fields": list(sample_fields),
                    "sample_records": data[:3],  # Include first 3 records as samples
                }
            )

            evidence.update(
                {
                    "records_found": breach_count,
                    "breach_sources": list(breach_sources),
                    "data_preview": data[:10],  # Store first 10 records
                }
            )

            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.FOUND,
                http_status=response.status_code,
                elapsed_ms=elapsed,
                evidence=evidence,
                profile=profile,
                timestamp_iso=ts,
            )

        except Exception as e:
            print(f"[ERROR] BreachVIP response parsing failed: {e}")
            return ProviderResult(
                provider=self.name,
                username=username,
                url=self.build_url(username),
                status=ResultStatus.ERROR,
                http_status=response.status_code,
                elapsed_ms=elapsed,
                evidence=evidence,
                profile=profile,
                error=f"Response parsing failed: {e}",
                timestamp_iso=ts,
            )


PROVIDERS = [BreachVIPProvider()]
