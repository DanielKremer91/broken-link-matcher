"""Live checks: is the target still dead, and does the referring page still link to it?"""

from __future__ import annotations

import time
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from blm.models import BrokenBacklink, MatchResult
from blm.wayback import USER_AGENT

DEAD_CODES = {404, 410}
MAX_HTML_BYTES = 2_000_000
_DEFAULT_PORTS = (":80", ":443")
# Malformed URLs from third-party exports: httpx.InvalidURL (bad port or IPv6 literal),
# UnicodeError (invalid IDNA host), ValueError (urllib parsing).
REQUEST_ERRORS = (httpx.HTTPError, httpx.InvalidURL, UnicodeError, ValueError)


def canonical(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    for port in _DEFAULT_PORTS:
        if host.endswith(port):
            host = host[: -len(port)]
            break
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def _request_kwargs(timeout: float) -> dict:
    return {"timeout": timeout, "follow_redirects": True, "headers": {"User-Agent": USER_AGENT}}


def target_status(url: str, client: httpx.Client, timeout: float = 10.0) -> Optional[int]:
    """Final HTTP status of the target (headers only, body is never read); None on network error."""
    try:
        with client.stream("GET", url, **_request_kwargs(timeout)) as response:
            return response.status_code
    except REQUEST_ERRORS:
        return None


def _page_links_to(html: bytes | str, page_url: str, target: str) -> bool:
    wanted = canonical(target)
    soup = BeautifulSoup(html, "lxml")
    base = soup.find("base", href=True)
    base_url = urljoin(page_url, base["href"]) if base else page_url
    for a in soup.find_all("a", href=True):
        try:
            if canonical(urljoin(base_url, a["href"])) == wanted:
                return True
        except ValueError:  # malformed href, e.g. an unclosed IPv6 literal
            continue
    return False


def _fetch_html(url: str, client: httpx.Client, timeout: float) -> Optional[tuple[bytes, str]]:
    """Return (first MAX_HTML_BYTES of the body, final URL) or None if not a usable HTML page."""
    with client.stream("GET", url, **_request_kwargs(timeout)) as response:
        if response.status_code >= 400:
            return None
        if "html" not in response.headers.get("content-type", "").lower():
            return None
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) >= MAX_HTML_BYTES:
                break
        return bytes(body[:MAX_HTML_BYTES]), str(response.url)


def verify_backlink(
    bl: BrokenBacklink,
    client: httpx.Client,
    timeout: float = 10.0,
    status_cache: Optional[dict] = None,
) -> str:
    if status_cache is not None and bl.url_to in status_cache:
        status = status_cache[bl.url_to]
    else:
        status = target_status(bl.url_to, client, timeout)
        if status_cache is not None:
            status_cache[bl.url_to] = status
    if status is None:
        return "unknown"
    if status not in DEAD_CODES:
        return "fixed" if status < 400 else "unknown"
    try:
        page = _fetch_html(bl.url_from, client, timeout)
        if page is None:
            return "unknown"
        body, final_url = page
        return "confirmed" if _page_links_to(body, final_url, bl.url_to) else "fixed"
    except REQUEST_ERRORS:
        return "unknown"


def verify_results(
    results: list[MatchResult],
    client: httpx.Client,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    pause: float = 0.5,
    progress: Optional[Callable[[int, int], None]] = None,
) -> None:
    last_host = None
    status_cache: dict = {}
    for i, row in enumerate(results, start=1):
        try:
            host = urlparse(row.backlink.url_from).netloc.lower()
        except ValueError:
            host = row.backlink.url_from
        if last_host is not None and host != last_host:
            sleeper(pause)
        try:
            row.verification = verify_backlink(row.backlink, client, status_cache=status_cache)
        except Exception:  # last resort: one odd row must not abort the whole run
            row.verification = "unknown"
        last_host = host
        if progress:
            progress(i, len(results))
