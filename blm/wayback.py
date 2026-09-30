"""Recover the content of a dead URL from the Wayback Machine.

Always uses the newest snapshot with HTTP status 200. Fetches the raw archived
HTML with the ``id_`` flag so no Wayback toolbar or rewritten links end up in
the text. Falls back to a plain concatenation of fields Ahrefs already
delivered; nothing is generated.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict, replace
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from blm.cache import JsonCache
from blm.models import BrokenBacklink, RecoveredContent

CDX_URL = "https://web.archive.org/cdx/search/cdx"
RETRY_PAUSES = (2, 4, 8)
REQUEST_PAUSE = 1.0  # between the CDX query and the snapshot fetch of one URL
CACHE_MAX_CHARS = 50000  # texts are cached at the UI maximum and cut per request
_EXT_RE = re.compile(r"\.(html?|php|aspx?|jsp)$", re.IGNORECASE)


def user_agent(contact: Optional[str] = None) -> str:
    """User-Agent for Wayback and live checks; a contact (e-mail or URL) lets site owners reach the operator."""
    # printable ASCII only: header values must not carry line breaks or non-ASCII characters
    clean = "".join(ch for ch in (contact or "") if " " <= ch <= "~")
    clean = " ".join(clean.replace("(", " ").replace(")", " ").split())[:200]
    suffix = f"; contact: {clean}" if clean else ""
    return f"broken-link-matcher/0.1 (SEO research tool; polite crawler, 1 req/s{suffix})"


USER_AGENT = user_agent()


class WaybackError(Exception):
    pass


def _get_with_retry(
    client: httpx.Client,
    url: str,
    params: Optional[dict],
    sleeper: Callable[[float], None],
    agent: str = USER_AGENT,
) -> httpx.Response:
    last_error = "unknown"
    for attempt in range(len(RETRY_PAUSES) + 1):
        try:
            resp = client.get(url, params=params, headers={"User-Agent": agent}, timeout=30.0, follow_redirects=True)
        except httpx.RequestError as exc:
            last_error = str(exc)
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
            else:
                return resp
        if attempt < len(RETRY_PAUSES):
            sleeper(RETRY_PAUSES[attempt])
    raise WaybackError(f"Wayback request failed after retries: {last_error}")


def latest_snapshot(
    url: str,
    client: httpx.Client,
    sleeper: Callable[[float], None] = time.sleep,
    agent: str = USER_AGENT,
) -> Optional[tuple[str, str]]:
    """Return (timestamp, original_url) of the newest 200 snapshot, or None."""
    params = {"url": url, "output": "json", "filter": "statuscode:200", "fl": "timestamp,original", "limit": "-1"}
    resp = _get_with_retry(client, CDX_URL, params, sleeper, agent)
    if resp.status_code != 200 or not resp.content.strip():
        return None
    try:
        rows = resp.json()
        if len(rows) < 2:
            return None
        timestamp, original = rows[-1][0], rows[-1][1]
    except (ValueError, IndexError, TypeError, KeyError) as exc:
        raise WaybackError(f"CDX response not parseable: {exc}") from exc
    return str(timestamp), str(original)


def snapshot_url(timestamp: str, original: str) -> str:
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def extract_text(html: str | bytes) -> str:
    """Extract the main text. Bytes are preferred: the parsers detect the charset themselves."""
    text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
    if text and text.strip():
        return text.strip()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.body or soup
    return body.get_text(" ", strip=True)


def slug_words(url: str) -> str:
    path = unquote(urlparse(url).path)
    path = _EXT_RE.sub("", path)
    words = re.sub(r"[-_/.+]+", " ", path)
    return re.sub(r"\s+", " ", words).strip()


def fallback_text(backlink: BrokenBacklink) -> Optional[str]:
    """Concatenate fields Ahrefs already delivered. Returns None if all are empty."""
    parts = [p.strip() for p in (backlink.title_from, backlink.anchor, backlink.snippet_left, backlink.snippet_right) if p and p.strip()]
    slug = slug_words(backlink.url_to)
    if slug:
        parts.append(slug)
    if not parts:
        return None
    return ". ".join(p.rstrip(".") for p in parts)


def fallback_content(backlink: BrokenBacklink, error: Optional[str], max_chars: int = 12000) -> RecoveredContent:
    """Result for a URL without usable snapshot, built from this backlink's own Ahrefs fields."""
    fallback = fallback_text(backlink)
    if fallback is None:
        return RecoveredContent(url_to=backlink.url_to, text=None, source="none", error=error)
    return RecoveredContent(url_to=backlink.url_to, text=fallback[:max_chars], source="fallback", error=error)


def _cached(cache: JsonCache, url: str, max_chars: int) -> Optional[RecoveredContent]:
    """Cached snapshot text cut to max_chars; malformed entries count as a miss."""
    hit = cache.get("wayback", url)
    if hit is None:
        return None
    try:
        rc = RecoveredContent(**hit)
    except (TypeError, KeyError):
        return None
    if not isinstance(rc.text, str) or not rc.text:
        return None
    return replace(rc, text=rc.text[:max_chars])


def recover_content(
    backlink: BrokenBacklink,
    client: httpx.Client,
    cache: Optional[JsonCache],
    *,
    max_chars: int = 12000,
    sleeper: Callable[[float], None] = time.sleep,
    user_agent: Optional[str] = None,
) -> RecoveredContent:
    """Newest 200 snapshot text (cut to max_chars) or the fallback. ``user_agent`` is the full header value."""
    url = backlink.url_to
    agent = user_agent or USER_AGENT
    if cache is not None:
        hit = _cached(cache, url, max_chars)
        if hit is not None:
            return hit

    error: Optional[str] = None
    try:
        snap = latest_snapshot(url, client, sleeper, agent)
        if snap is not None:
            timestamp, original = snap
            sleeper(REQUEST_PAUSE)
            resp = _get_with_retry(client, snapshot_url(timestamp, original), None, sleeper, agent)
            text = extract_text(resp.content)[:CACHE_MAX_CHARS] if resp.status_code == 200 else ""
            if text:
                result = RecoveredContent(url_to=url, text=text, source="wayback", snapshot_timestamp=timestamp)
                if cache is not None:
                    cache.set("wayback", url, asdict(result))
                return replace(result, text=text[:max_chars])
            error = "Snapshot ohne extrahierbaren Text"
        else:
            error = "Kein Snapshot mit Status 200"
    except WaybackError as exc:
        error = f"Wayback-Fehler: {exc}"

    return fallback_content(backlink, error, max_chars)
