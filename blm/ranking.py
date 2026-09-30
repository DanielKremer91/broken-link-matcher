"""Prioritise linking pages: filter, sort, cap, and assign value_rank."""

from __future__ import annotations

from dataclasses import replace

from blm.models import BrokenBacklink

SORT_FIELDS = ("domain_rating", "url_rating", "page_traffic")


def _desc_key(value):
    """Sort key for descending order with None last."""
    return (value is None, -(value or 0))


def rank_backlinks(
    backlinks: list[BrokenBacklink],
    *,
    dofollow_only: bool = True,
    content_only: bool = True,
    min_dr: float = 0.0,
    sort_by: str = "domain_rating",
    limit: int = 100,
) -> list[BrokenBacklink]:
    if sort_by not in SORT_FIELDS:
        raise ValueError(f"Unbekanntes Sortierkriterium: {sort_by}")

    kept = []
    for bl in backlinks:
        if dofollow_only and bl.is_dofollow is False:
            continue
        if content_only and bl.is_content is False:
            continue
        if min_dr > 0 and bl.domain_rating is not None and bl.domain_rating < min_dr:
            continue
        kept.append(bl)

    kept.sort(key=lambda b: (_desc_key(getattr(b, sort_by)), _desc_key(b.page_traffic)))
    return [replace(b, value_rank=i + 1) for i, b in enumerate(kept[:limit])]
