"""Parse the Screaming Frog embeddings export into OwnPage objects.

The file is read with the shared table reader (CSV/TSV/TXT in any common encoding
and delimiter, or Excel). Two layouts are supported:
1. Wide (verified against SF 24.3): column ``url`` then ``embedding_0`` ...
   ``embedding_N`` with one float per column.
2. Single column: a URL column plus one column holding a list such as
   ``[0.1, 0.2, ...]`` or ``0.1,0.2,...`` (UI export, e.g. "Embeddings Fressnapf 1").

If the columns are not recognised, callers can name them via ``url_col`` and
``vector_col`` (the app offers a mapping form built on ``detect_frog_columns``).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from blm.ingest.tables import TableInfo, read_table_info
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
    table: Optional[TableInfo] = None  # how the file was read, for the UI caption


@dataclass
class FrogColumns:
    url_col: Optional[str]
    vector_col: Optional[str]
    wide: bool
    columns: list[str]
    wide_cols: list[str] = field(default_factory=list)
    title_col: Optional[str] = None


def _find_column(columns: dict[str, str], candidates: tuple[str, ...]) -> Optional[str]:
    for cand in candidates:
        if cand in columns:
            return columns[cand]
    return None


def _find_fuzzy_vector_column(columns: dict[str, str], url_col: Optional[str]) -> Optional[str]:
    """Screaming Frog names the UI export column after the extractor ("Embeddings Fressnapf 1").

    Accept the first column whose name contains "embed" or "vector", except the URL
    column and columns that obviously hold a model name rather than numbers.
    """
    for lowered, original in columns.items():
        if original == url_col:
            continue
        if ("embed" in lowered or "vector" in lowered) and "model" not in lowered:
            return original
    return None


MIN_CONTENT_DIMENSION = 32  # shorter number lists are ordinary data, not embeddings


def _find_vector_by_content(df: pd.DataFrame, skip: set) -> Optional[str]:
    """Column whose first filled cells mostly parse as number lists of one length >= 32.

    Custom JavaScript extractors carry arbitrary names ("BORA MC Extraction 1").
    """
    for col in df.columns:
        if col in skip:
            continue
        sample = [v for v in df[col].head(200).tolist() if str(v).strip()][:10]
        if not sample:
            continue
        sizes = Counter(v.size for v in map(_parse_vector, sample) if v is not None and v.size >= MIN_CONTENT_DIMENSION)
        # an error text from the snippet in a few cells must not hide the column
        if sizes and max(sizes.values()) * 2 > len(sample):
            return str(col)
    return None


def detect_frog_columns(df: pd.DataFrame) -> FrogColumns:
    """Guess URL, title and vector columns. Wide ``embedding_N`` columns take precedence."""
    names = [str(c) for c in df.columns]
    lowered = {c.strip().lower(): c for c in names}
    url_col = _find_column(lowered, URL_CANDIDATES)
    wide_cols = sorted(
        (c for c in names if _WIDE_RE.fullmatch(c.strip())),
        key=lambda c: int(_WIDE_RE.fullmatch(c.strip()).group(1)),
    )
    vector_col = None
    if not wide_cols:
        vector_col = (_find_column(lowered, VECTOR_CANDIDATES) or _find_fuzzy_vector_column(lowered, url_col)
                      or _find_vector_by_content(df, {url_col}))
    return FrogColumns(
        url_col=url_col,
        vector_col=vector_col,
        wide=bool(wide_cols),
        columns=names,
        wide_cols=wide_cols,
        title_col=_find_column(lowered, TITLE_CANDIDATES),
    )


def _parse_vector(raw) -> Optional[np.ndarray]:
    """Parse '0.1,0.2', '[0.1, 0.2]', '0.1 0.2', '0.1;0.2' or (German Excel) '0,1;0,2'.

    Decimal commas are only accepted when ';' separates the values; with ',' as the
    separator they would be ambiguous.
    """
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    text = str(raw).strip().strip("[]()")
    if not text:
        return None
    if ";" in text:
        parts = [p.strip().replace(",", ".") for p in text.split(";")]
        parts = [p for p in parts if p]
    else:
        parts = [p for p in re.split(r"[,\s]+", text) if p]
    try:
        vec = np.asarray([float(p) for p in parts], dtype=np.float32)
    except ValueError:
        return None
    if not vec.size or not np.isfinite(vec).all():
        return None
    return vec


def _columns_hint(columns: list[str]) -> str:
    return f" Gefundene Spalten: {', '.join(columns)}." if columns else ""


def load_frog_embeddings(source, *, url_col: Optional[str] = None, vector_col: Optional[str] = None) -> FrogImport:
    """Read a Screaming Frog embeddings export. Raises ValueError (German) on unusable input.

    ``url_col`` and ``vector_col`` override the detected columns; a given ``vector_col``
    is read as a single list column even if wide ``embedding_N`` columns exist.
    """
    df, info = read_table_info(source)
    detected = detect_frog_columns(df)
    hint = _columns_hint(detected.columns)
    for given in (url_col, vector_col):
        if given is not None and given not in detected.columns:
            raise ValueError(f"Spalte '{given}' nicht gefunden.{hint}")

    url = url_col or detected.url_col
    if url is None:
        raise ValueError(f"Keine URL-Spalte gefunden (erwartet 'url' oder 'Address').{hint}")
    wide_cols = [] if vector_col is not None else detected.wide_cols
    vec_col = None if wide_cols else (vector_col or detected.vector_col)
    if vec_col is not None and vec_col == url:
        if vector_col is not None:
            raise ValueError("URL- und Embedding-Spalte müssen verschieden sein.")
        vec_col = None  # a manual url_col pointed at the detected vector column
    if not wide_cols and vec_col is None:
        raise ValueError(
            "Keine Embedding-Spalten gefunden (erwartet 'embedding_0 ...' oder eine Spalte, "
            f"deren Name 'Embed' oder 'Vector' enthält, z. B. 'Embeddings Fressnapf 1').{hint}"
        )
    title_col = detected.title_col if detected.title_col not in (url, vec_col) else None

    if wide_cols:
        # read_table returns strings; blanks and junk become NaN and skip the row
        # (decimal commas from German Excel are accepted)
        text = df[wide_cols].apply(lambda s: s.astype(str).str.replace(",", ".", regex=False))
        matrix = text.apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
        vectors = [row.copy() if np.isfinite(row).all() else None for row in matrix]
    else:
        vectors = [_parse_vector(v) for v in df[vec_col].tolist()]
    titles = df[title_col].tolist() if title_col is not None else [""] * len(df)

    candidates: list[OwnPage] = []
    skipped = 0
    for raw_url, vec, title in zip(df[url].tolist(), vectors, titles):
        page_url = "" if _is_missing(raw_url) else str(raw_url).strip()
        if not page_url or vec is None:
            skipped += 1
            continue
        candidates.append(OwnPage(url=page_url, vector=vec, title="" if _is_missing(title) else str(title)))

    if not candidates:
        raise ValueError(f"Keine gültigen Embeddings in der Datei.{hint}")

    # A cell cut by Excel's 32767-character limit has fewer values than the rest: the
    # most common length wins (ties: the longer one, truncation only shortens), the
    # others are skipped.
    sizes = Counter(p.vector.size for p in candidates)
    dimension = max(sizes, key=lambda n: (sizes[n], n))
    pages = [p for p in candidates if p.vector.size == dimension]
    skipped += len(candidates) - len(pages)
    return FrogImport(pages=pages, dimension=int(dimension), skipped=skipped, table=info)


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and np.isnan(value))
