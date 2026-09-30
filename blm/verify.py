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


def canonical(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def _get(client: httpx.Client, url: str, timeout: float) -> httpx.Response:
    return client.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _page_links_to(html: str, page_url: str, target: str) -> bool:
    wanted = canonical(target)
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        if canonical(urljoin(page_url, a["href"])) == wanted:
            return True
    return False


def verify_backlink(bl: BrokenBacklink, client: httpx.Client, timeout: float = 10.0) -> str:
    try:
        target = _get(client, bl.url_to, timeout)
        if target.status_code not in DEAD_CODES:
            return "fixed"
        source = _get(client, bl.url_from, timeout)
        if source.status_code >= 400:
            return "unknown"
        return "confirmed" if _page_links_to(source.text, bl.url_from, bl.url_to) else "fixed"
    except httpx.HTTPError:
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
    for i, row in enumerate(results, start=1):
        host = urlparse(row.backlink.url_from).netloc.lower()
        if last_host is not None and host != last_host:
            sleeper(pause)
        row.verification = verify_backlink(row.backlink, client)
        last_host = host
        if progress:
            progress(i, len(results))
