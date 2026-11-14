"""Shared download helper with a local cache for raw dataset files.

Raw files are kept in `backend/.cache/data/raw/` (gitignored) and never
uploaded to MongoDB; only derived profiles are stored.
"""

from __future__ import annotations

import ssl
import urllib.request
from http.client import HTTPResponse
from pathlib import Path

try:
    import certifi

    _SSL_CONTEXT: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    # certifi isn't a hard dependency; fall back to the platform's default
    # trust store (this is what fails on some stock macOS Python installs).
    _SSL_CONTEXT = None

RAW_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "data" / "raw"
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


def urlopen(url: str, timeout: float) -> HTTPResponse:
    if not url.startswith("https://"):
        raise ValueError("only https downloads are allowed")
    return urllib.request.urlopen(url, timeout=timeout, context=_SSL_CONTEXT)  # noqa: S310


def fetch_cached(url: str, relative_path: str, timeout: float = 30.0) -> bytes:
    """Return the file at `url`, downloading it once into the raw cache."""
    path = (RAW_CACHE_DIR / relative_path).resolve()
    if RAW_CACHE_DIR.resolve() not in path.parents:
        raise ValueError("cache path escapes the raw cache directory")
    if path.exists():
        return path.read_bytes()

    with urlopen(url, timeout=timeout) as response:
        data = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"download larger than {MAX_DOWNLOAD_BYTES} bytes: {url}")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
    return data
