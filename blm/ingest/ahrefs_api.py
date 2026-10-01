"""Optional live fetch of broken backlinks from the Ahrefs API v3.

Costs API units per row; `traffic` costs 10 extra units per row and is only
requested when include_traffic is True.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

from blm.models import BrokenBacklink

AHREFS_URL = "https://api.ahrefs.com/v3/site-explorer/broken-backlinks"
BASE_SELECT = [
    "url_from", "url_to", "anchor", "snippet_left", "snippet_right", "title",
    "domain_rating_source", "url_rating_source", "http_code_target", "is_dofollow", "is_content",
]


class AhrefsError(Exception):
    pass


def _clean_language(language: Optional[str]) -> str:
    return (language or "").strip()


def _build_where(*, dofollow_only: bool, content_only: bool, exclude_spam: bool, dead_only: bool,
                 min_dr: float, language: Optional[str]) -> Optional[dict]:
    """Server-side filter expression; None when no condition is active."""
    conditions: list[dict] = []
    if dofollow_only:
        conditions.append({"field": "is_dofollow", "is": ["eq", True]})
    if content_only:
        conditions.append({"field": "is_content", "is": ["eq", True]})
    if exclude_spam:
        conditions.append({"field": "is_spam", "is": ["eq", False]})
    if dead_only:
        conditions.append({"or": [
            {"field": "http_code_target", "is": ["eq", 404]},
            {"field": "http_code_target", "is": ["eq", 410]},
        ]})
    if min_dr > 0:
        conditions.append({"field": "domain_rating_source", "is": ["gte", min_dr]})
    if _clean_language(language):
        conditions.append({"field": "languages", "list_is": {"any": ["eq", _clean_language(language)]}})
    return {"and": conditions} if conditions else None


def describe_filters(
    *,
    dofollow_only: bool = True,
    content_only: bool = True,
    exclude_spam: bool = True,
    dead_only: bool = True,
    min_dr: float = 0.0,
    language: Optional[str] = None,
) -> str:
    """One-line German description of the active server-side filters, for the UI."""
    parts = []
    if dofollow_only:
        parts.append("Dofollow")
    if content_only:
        parts.append("Content-Links")
    if exclude_spam:
        parts.append("ohne Spam")
    if dead_only:
        parts.append("nur 404/410")
    if min_dr > 0:
        parts.append(f"DR ≥ {min_dr:g}")
    if _clean_language(language):
        parts.append(f"Sprache {_clean_language(language)}")
    return " · ".join(parts) or "keine Filter"


def fetch_broken_backlinks(
    token: str,
    target: str,
    *,
    limit: int = 100,
    include_traffic: bool = False,
    dofollow_only: bool = True,
    content_only: bool = True,
    exclude_spam: bool = True,
    dead_only: bool = True,
    min_dr: float = 0.0,
    language: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> list[BrokenBacklink]:
    if not token:
        raise AhrefsError("Ahrefs-API-Schlüssel fehlt.")
    if not target or not target.strip():
        raise AhrefsError("Wettbewerber-Domain fehlt.")
    target = target.strip()
    select = BASE_SELECT + (["traffic"] if include_traffic else [])
    params = {
        "target": target,
        "mode": "subdomains",
        "aggregation": "1_per_domain",
        "order_by": "domain_rating_source:desc",
        "select": ",".join(select),
        "limit": str(limit),
        "output": "json",
    }
    where = _build_where(dofollow_only=dofollow_only, content_only=content_only, exclude_spam=exclude_spam,
                         dead_only=dead_only, min_dr=min_dr, language=language)
    if where is not None:
        params["where"] = json.dumps(where)
    own_client = client is None
    client = client or httpx.Client(timeout=60.0)
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        }
        resp = client.get(AHREFS_URL, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise AhrefsError(f"Ahrefs-Anfrage fehlgeschlagen: {exc}") from exc
    finally:
        if own_client:
            client.close()
    if resp.status_code >= 400:
        raise AhrefsError(f"Ahrefs API HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
    except ValueError as exc:
        raise AhrefsError(
            f"Ahrefs API: Antwort ist kein JSON: {resp.text[:300]}"
        ) from exc
    if not isinstance(data, dict) or "backlinks" not in data:
        raise AhrefsError(
            f"Ahrefs API: unerwartete Antwort ohne 'backlinks': {resp.text[:300]}"
        )

    rows = []
    for item in data["backlinks"] or []:
        url_from = item.get("url_from")
        url_to = item.get("url_to")
        if not url_from or not url_to:
            continue  # incomplete row, cannot be matched
        rows.append(BrokenBacklink(
            url_from=url_from,
            url_to=url_to,
            anchor=item.get("anchor") or "",
            snippet_left=item.get("snippet_left") or "",
            snippet_right=item.get("snippet_right") or "",
            title_from=item.get("title") or "",
            domain_rating=item.get("domain_rating_source"),
            url_rating=item.get("url_rating_source"),
            page_traffic=item.get("traffic"),
            is_dofollow=bool(item["is_dofollow"]) if item.get("is_dofollow") is not None else None,
            is_content=bool(item["is_content"]) if item.get("is_content") is not None else None,
            http_code_target=item.get("http_code_target"),
        ))
    return rows
