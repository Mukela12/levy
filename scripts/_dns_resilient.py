"""Import this first to survive a flaky local DNS resolver.

Some networks (a home router that resolves CDN-fronted hosts unreliably, or a
VPN with split DNS) make socket.getaddrinfo fail intermittently with
EAI_NONAME for hosts that public DNS resolves fine (Supabase, OpenAI, Railway,
judiciaryzambia.com all sit behind Cloudflare). This shim leaves normal
resolution untouched and only on failure falls back to querying public DNS
(1.1.1.1 / 8.8.8.8) via the `host` command, caching the result for the run.

The pinned IPs are Cloudflare anycast addresses; TLS still works because the
SNI carries the real hostname. Import order matters: import this module before
creating any HTTP client so the patch is in place.
"""
from __future__ import annotations
import socket
import subprocess

_orig_getaddrinfo = socket.getaddrinfo
_cache: dict[str, str] = {}


def _resolve_via_public_dns(host: str) -> str | None:
    if host in _cache:
        return _cache[host]
    for dns in ("1.1.1.1", "8.8.8.8"):
        try:
            out = subprocess.run(
                ["host", "-W", "5", host, dns],
                capture_output=True, text=True, timeout=8,
            ).stdout
        except Exception:
            continue
        for line in out.splitlines():
            if "has address" in line:
                ip = line.rsplit("has address", 1)[-1].strip()
                if ip:
                    _cache[host] = ip
                    return ip
    return None


def _patched_getaddrinfo(host, port, *args, **kwargs):
    try:
        return _orig_getaddrinfo(host, port, *args, **kwargs)
    except socket.gaierror:
        if not isinstance(host, str):
            raise
        ip = _resolve_via_public_dns(host)
        if not ip:
            raise
        p = port if isinstance(port, int) else 0
        # IPv4 TCP result tuple; good enough for httpx/openai/supabase clients.
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, p))]


socket.getaddrinfo = _patched_getaddrinfo
