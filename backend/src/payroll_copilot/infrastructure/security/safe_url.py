"""SSRF-safe URL validation for legal source fetching.

Only https URLs to public hosts may be fetched. Private/link-local/metadata
addresses and unexpected schemes are rejected. Redirect targets must also pass.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeSourceUrlError(ValueError):
    """Raised when a URL is not allowed for outbound legal-source fetch."""


def assert_safe_public_https_url(url: str, *, allow_hosts: set[str] | None = None) -> str:
    """Validate URL for outbound fetch. Returns normalized URL string."""
    raw = (url or "").strip()
    if not raw:
        raise UnsafeSourceUrlError("empty_url")
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise UnsafeSourceUrlError("scheme_not_https")
    if not parsed.hostname:
        raise UnsafeSourceUrlError("missing_hostname")
    host = parsed.hostname.lower().rstrip(".")
    if allow_hosts is not None and host not in {h.lower() for h in allow_hosts}:
        raise UnsafeSourceUrlError(f"host_not_allowlisted:{host}")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".localhost"):
        raise UnsafeSourceUrlError("localhost_blocked")
    _assert_public_host(host)
    return raw


def _assert_public_host(host: str) -> None:
    # Block literal IPs that are private/reserved.
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeSourceUrlError(f"private_or_reserved_ip:{host}")
        return
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeSourceUrlError(f"dns_resolution_failed:{host}") from exc
    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeSourceUrlError(f"resolves_to_private_ip:{host}->{ip_str}")
