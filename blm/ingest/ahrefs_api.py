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
    "domain_rating_source", "url_rating_source", "http_code_target",
]


class AhrefsError(Exception):
    pass


def fetch_broken_backlinks(
    token: str,
    target: str,
    *,
    limit: int = 100,
    include_traffic: bool = False,
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
        "where": json.dumps({"and": [
            {"field": "is_dofollow", "is": ["eq", True]},
            {"field": "is_content", "is": ["eq", True]},
        ]}),
        "order_by": "domain_rating_source:desc",
        "select": ",".join(select),
        "limit": str(limit),
        "output": "json",
    }
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
            is_dofollow=True,
            is_content=True,
            http_code_target=item.get("http_code_target"),
        ))
    return rows
