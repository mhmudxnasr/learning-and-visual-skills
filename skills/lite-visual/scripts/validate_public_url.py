#!/usr/bin/env python3
"""Fail unless one URL resolves exclusively to public Internet addresses."""

from __future__ import annotations

import ipaddress
import socket
import sys
from urllib.parse import urlparse


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_public_url.py URL", file=sys.stderr)
        return 2
    parsed = urlparse(sys.argv[1])
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        print("URL must be public HTTP(S) without embedded credentials", file=sys.stderr)
        return 1
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
    except (OSError, ValueError) as exc:
        print(f"URL hostname did not resolve: {exc}", file=sys.stderr)
        return 1
    if not addresses:
        print("URL hostname resolved to no addresses", file=sys.stderr)
        return 1
    for address in addresses:
        if not ipaddress.ip_address(address.split("%", 1)[0]).is_global:
            print("URL resolves to a private, local, reserved, or otherwise non-public address", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
