"""Parse the Screaming Frog embeddings export into OwnPage objects.

Two layouts are supported:
1. Wide (verified against SF 24.3): column ``url`` then ``embedding_0`` ...
   ``embedding_N`` with one float per column.
2. Single column: a URL column plus one column holding a list such as
   ``[0.1, 0.2, ...]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from blm.models import OwnPage

URL_CANDIDATES = ("url", "address", "adresse")
TITLE_CANDIDATES = ("title", "title 1", "titel")
VECTOR_CANDIDATES = ("embedding", "embeddings", "vector", "embedding vector")
_WIDE_RE = re.compile(r"embedding_(\d+)", re.IGNORECASE)


@dataclass
class FrogImport:
    pages: list[OwnPage]
    dimension: int
    skipped: int


def _find_column(columns: dict[str, str], candidates: tuple[str, ...]) -> Optional[str]:
    for cand in candidates:
        if cand in columns:
            return columns[cand]
    return None


def _parse_vector(raw) -> Optional[np.ndarray]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    text = str(raw).strip().strip("[]()")
    if not text:
        return None
    parts = [p for p in re.split(r"[,\s]+", text) if p]
    try:
        vec = np.asarray([float(p) for p in parts], dtype=np.float32)
    except ValueError:
        return None
    return vec if vec.size else None


def load_frog_embeddings(source) -> FrogImport:
    """Read a Screaming Frog embeddings CSV. Raises ValueError on unusable input."""
    df = pd.read_csv(source, encoding="utf-8-sig")
    columns = {str(c).strip().lower(): c for c in df.columns}

    url_col = _find_column(columns, URL_CANDIDATES)
    if url_col is None:
        raise ValueError("Keine URL-Spalte gefunden (erwartet 'url' oder 'Address').")
    title_col = _find_column(columns, TITLE_CANDIDATES)

    wide_cols = sorted(
        (c for c in df.columns if _WIDE_RE.fullmatch(str(c).strip())),
        key=lambda c: int(_WIDE_RE.fullmatch(str(c).strip()).group(1)),
    )
    vector_col = None if wide_cols else _find_column(columns, VECTOR_CANDIDATES)
    if not wide_cols and vector_col is None:
        raise ValueError(
            "Keine Embedding-Spalten gefunden (erwartet 'embedding_0 ...' oder eine Spalte 'Embeddings')."
        )

    pages: list[OwnPage] = []
    skipped = 0
    for _, row in df.iterrows():
        if wide_cols:
            values = pd.to_numeric(row[wide_cols], errors="coerce").to_numpy(dtype=np.float32)
            vec = None if np.isnan(values).any() else values
        else:
            vec = _parse_vector(row[vector_col])
        if vec is None:
            skipped += 1
            continue
        title = ""
        if title_col is not None and pd.notna(row[title_col]):
            title = str(row[title_col])
        pages.append(OwnPage(url=str(row[url_col]).strip(), vector=vec, title=title))

    if not pages:
        raise ValueError("Keine gültigen Embeddings in der Datei.")

    dimension = int(pages[0].vector.size)
    consistent = [p for p in pages if p.vector.size == dimension]
    skipped += len(pages) - len(consistent)
    return FrogImport(pages=consistent, dimension=dimension, skipped=skipped)
