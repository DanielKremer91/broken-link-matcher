"""Dataclasses shared by every pipeline step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class BrokenBacklink:
    """One broken backlink pointing at a competitor URL."""

    url_from: str
    url_to: str
    anchor: str = ""
    snippet_left: str = ""
    snippet_right: str = ""
    title_from: str = ""
    domain_rating: Optional[float] = None
    url_rating: Optional[float] = None
    page_traffic: Optional[int] = None
    is_dofollow: Optional[bool] = None
    is_content: Optional[bool] = None
    http_code_target: Optional[int] = None
    value_rank: Optional[int] = None


@dataclass
class OwnPage:
    """One page of the user's own domain with its Screaming Frog embedding."""

    url: str
    vector: np.ndarray
    title: str = ""


@dataclass
class RecoveredContent:
    """Text recovered for a dead competitor URL.

    source is one of: "wayback", "fallback", "none".
    """

    url_to: str
    text: Optional[str]
    source: str
    snapshot_timestamp: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Match:
    url: str
    score: float


@dataclass
class MatchResult:
    """Final row: backlink, recovered text, top matches and bookkeeping.

    verification is one of: "confirmed", "fixed", "unknown", "skipped".
    """

    backlink: BrokenBacklink
    recovered: RecoveredContent
    top: list[Match] = field(default_factory=list)
    is_content_gap: bool = False
    value_rank: int = 0
    priority: int = 0
    verification: str = "skipped"
    errors: list[str] = field(default_factory=list)
