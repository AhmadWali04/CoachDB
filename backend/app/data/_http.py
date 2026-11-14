"""Shared urllib helper. Isolated so both source adapters fetch the same way
and so the SSL-certificate workaround below lives in exactly one place.
"""

from __future__ import annotations

import ssl
import urllib.request
from http.client import HTTPResponse

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # certifi isn't a hard dependency; fall back to the platform's default
    # trust store (this is what fails on some stock macOS Python installs).
    _SSL_CONTEXT = None


def urlopen(url: str, timeout: float) -> HTTPResponse:
    return urllib.request.urlopen(url, timeout=timeout, context=_SSL_CONTEXT)  # noqa: S310
