"""Cosine-similarity matching of recovered competitor texts against own pages.

Pure numpy and sorting; no IO.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from blm.models import BrokenBacklink, Match, MatchResult, OwnPage, RecoveredContent


def normalize_rows(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def top_k(query: np.ndarray, own_matrix: np.ndarray, urls: list[str], k: int = 3) -> list[Match]:
    q = np.asarray(query, dtype=np.float32)
    norm = np.linalg.norm(q)
    if norm == 0:
        return []
    scores = own_matrix @ (q / norm)
    k = min(k, len(urls))
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [Match(url=urls[i], score=float(scores[i])) for i in idx]


def build_results(
    ranked: list[BrokenBacklink],
    recovered: list[RecoveredContent],
    vectors: list[Optional[np.ndarray]],
    own_pages: list[OwnPage],
    *,
    threshold: float = 0.5,
    match_fallback: bool = True,
) -> list[MatchResult]:
    if not (len(ranked) == len(recovered) == len(vectors)):
        raise ValueError("ranked, recovered und vectors müssen gleich lang sein")

    own_matrix = normalize_rows(np.stack([p.vector for p in own_pages]))
    urls = [p.url for p in own_pages]

    matched: list[MatchResult] = []
    gaps: list[MatchResult] = []
    unmatched: list[MatchResult] = []
    for bl, rc, vec in zip(ranked, recovered, vectors):
        row = MatchResult(backlink=bl, recovered=rc, value_rank=bl.value_rank or 0)
        if rc.error:
            row.errors.append(rc.error)
        if rc.text is None:
            row.errors.append("Nicht gematcht: kein Text (kein Snapshot, keine Ahrefs-Felder)")
            unmatched.append(row)
            continue
        if rc.source == "fallback" and not match_fallback:
            row.errors.append("Nicht gematcht: Fallback-Zeilen sind ausgeschlossen")
            unmatched.append(row)
            continue
        if vec is None:
            row.errors.append("Nicht gematcht: Embedding fehlgeschlagen")
            unmatched.append(row)
            continue
        row.top = top_k(vec, own_matrix, urls, k=3)
        best = row.top[0].score if row.top else 0.0
        row.is_content_gap = best < threshold
        (gaps if row.is_content_gap else matched).append(row)

    ordered = sorted(matched, key=lambda r: r.value_rank) + sorted(gaps, key=lambda r: r.value_rank) + sorted(unmatched, key=lambda r: r.value_rank)
    for i, row in enumerate(ordered, start=1):
        row.priority = i
    return ordered
