from __future__ import annotations

import ipaddress
import socket
from typing import Iterable, Optional, Tuple

import httpx


class UnsafeURLError(ValueError):
    pass


def _is_ip_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except Exception:
        return True

    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def _resolve_host_ips(host: str) -> Iterable[str]:
    # getaddrinfo can return duplicates; dedupe.
    seen = set()
    for fam, _, _, _, sockaddr in socket.getaddrinfo(host, None):
        if fam == socket.AF_INET:
            ip = sockaddr[0]
        elif fam == socket.AF_INET6:
            ip = sockaddr[0]
        else:
            continue
        if ip not in seen:
            seen.add(ip)
            yield ip


def assert_url_safe(url: str) -> None:
    """Basic SSRF defense for addon fetches.

    Blocks:
    - non-http(s) schemes
    - localhost-ish hosts
    - hosts that resolve to private/link-local/etc IP space
    """
    try:
        u = httpx.URL(url)
    except Exception as e:
        raise UnsafeURLError(f"bad url: {e}")

    if u.scheme not in ("http", "https"):
        raise UnsafeURLError("scheme not allowed")

    host = (u.host or "").strip().lower()
    if not host:
        raise UnsafeURLError("missing host")

    if host in ("localhost", "localhost.localdomain"):
        raise UnsafeURLError("localhost blocked")

    # block common cloud metadata names
    if host in (
        "metadata.google.internal",
        "metadata",
        "169.254.169.254",
    ):
        raise UnsafeURLError("metadata host blocked")

    # If host is an IP literal, validate directly.
    try:
        ipaddress.ip_address(host)
        if _is_ip_blocked(host):
            raise UnsafeURLError("ip blocked")
        return
    except ValueError:
        pass

    # Otherwise resolve and block if ANY address is unsafe.
    for ip in _resolve_host_ips(host):
        if _is_ip_blocked(ip):
            raise UnsafeURLError("host resolves to blocked ip")


async def safe_fetch_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    timeout: float = 10.0,
    max_bytes: int = 2_000_000,
    accept_prefix: Optional[str] = None,
    max_redirects: int = 3,
) -> Tuple[bytes, str]:
    """Fetch bytes from a URL with SSRF and size controls.

    Returns (content_bytes, content_type).
    """
    next_url = url
    for _ in range(max_redirects + 1):
        assert_url_safe(next_url)

        headers = {}
        if accept_prefix:
            headers["Accept"] = f"{accept_prefix}/*"

        async with client.stream(
            "GET",
            next_url,
            follow_redirects=False,
            timeout=timeout,
            headers=headers,
        ) as r:
            # handle redirects manually (validate new location)
            if r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("location")
                if not loc:
                    raise UnsafeURLError("redirect without location")
                next_url = str(httpx.URL(next_url).join(loc))
                continue

            if r.status_code < 200 or r.status_code >= 300:
                raise httpx.HTTPStatusError(
                    f"bad status {r.status_code}", request=r.request, response=r
                )

            ctype = (r.headers.get("content-type") or "").split(";")[0].strip().lower()
            if accept_prefix and not ctype.startswith(f"{accept_prefix}/"):
                raise UnsafeURLError("unexpected content-type")

            clen = r.headers.get("content-length")
            if clen:
                try:
                    if int(clen) > max_bytes:
                        raise UnsafeURLError("content too large")
                except ValueError:
                    pass

            buf = bytearray()
            async for chunk in r.aiter_bytes():
                if not chunk:
                    continue
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise UnsafeURLError("content too large")

            return bytes(buf), ctype

    raise UnsafeURLError("too many redirects")
