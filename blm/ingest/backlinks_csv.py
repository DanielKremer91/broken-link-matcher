"""Read a broken-backlinks table (Ahrefs UI export, Ahrefs API/MCP output, or any
other tool) and normalise it into BrokenBacklink objects.

Column detection is alias based. Extend FIELD_ALIASES to support more tools.
"""

from __future__ import annotations

import csv
import io
import math
import numbers
import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from blm.models import BrokenBacklink

REQUIRED_FIELDS = ("url_from", "url_to")
OPTIONAL_FIELDS = (
    "anchor",
    "snippet_left",
    "snippet_right",
    "title_from",
    "domain_rating",
    "url_rating",
    "page_traffic",
    "is_dofollow",
    "is_nofollow",
    "is_content",
    "http_code_target",
)

# internal field -> lower-cased source column names (Ahrefs UI export, Ahrefs API, misc.)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "url_from": ("url_from", "referring page url", "referring page", "source url", "source page url", "source"),
    "url_to": ("url_to", "target url", "target page url", "broken url", "destination url", "target"),
    "anchor": ("anchor", "anchor text", "ankertext", "link anchor"),
    "snippet_left": ("snippet_left", "left context", "text before", "context left"),
    "snippet_right": ("snippet_right", "right context", "text after", "context right"),
    "title_from": ("title", "referring page title", "source title", "page title", "referring title"),
    "domain_rating": ("domain_rating_source", "domain rating", "dr", "source dr", "referring domain rating"),
    "url_rating": ("url_rating_source", "url rating", "ur", "source ur"),
    "page_traffic": ("traffic", "page traffic", "referring page traffic", "organic traffic"),
    "is_dofollow": ("is_dofollow", "dofollow", "follow"),
    "is_nofollow": ("is_nofollow", "nofollow"),
    "is_content": ("is_content", "content", "in content"),
    "http_code_target": ("http_code_target", "target url http code", "target http code", "http code target", "target status"),
}

_TRUE = {"true", "1", "1.0", "yes", "ja", "y", "dofollow", "follow", "x", "wahr"}
_FALSE = {"false", "0", "0.0", "no", "nein", "n", "nofollow", "falsch"}


@dataclass
class ColumnMapping:
    mapping: dict[str, str]
    missing: list[str]
    columns: list[str]


_ENCODINGS = ("utf-8-sig", "utf-16", "cp1252")
_SNIFF_BYTES = 64 * 1024


def _decode(data: bytes) -> str:
    for encoding in _ENCODINGS:
        # Without a BOM the utf-16 codec "succeeds" on almost any even-length input, so
        # only try it when a BOM is present.
        if encoding == "utf-16" and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Datei konnte nicht gelesen werden: Zeichenkodierung nicht erkannt")


def _sniff_delimiter(text: str) -> str:
    try:
        return csv.Sniffer().sniff(text[:_SNIFF_BYTES], delimiters=",;\t|").delimiter
    except csv.Error:
        return ","


def read_table(source, filename: Optional[str] = None) -> pd.DataFrame:
    """Read CSV or XLSX. `filename` is used for type detection when `source` is a stream.

    Raises ValueError with a German message if the file cannot be read.
    """
    name = (filename or getattr(source, "name", None) or str(source)).lower()
    try:
        if name.endswith((".xlsx", ".xlsm", ".xls")):
            return pd.read_excel(source)
        if hasattr(source, "read"):
            data = source.read()
        else:
            with open(source, "rb") as fh:
                data = fh.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        if not data.strip():
            raise ValueError("Datei ist leer")
        text = _decode(data)
        return pd.read_csv(
            io.StringIO(text), sep=_sniff_delimiter(text), dtype=str, keep_default_na=False
        )
    except ValueError as exc:
        if str(exc).startswith("Datei konnte nicht gelesen werden"):
            raise
        raise ValueError(f"Datei konnte nicht gelesen werden: {exc}") from exc
    except (OSError, csv.Error, pd.errors.ParserError) as exc:
        raise ValueError(f"Datei konnte nicht gelesen werden: {exc}") from exc


def detect_columns(df: pd.DataFrame) -> ColumnMapping:
    lowered = {str(c).strip().lower(): str(c) for c in df.columns}
    mapping: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field] = lowered[alias]
                break
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    return ColumnMapping(mapping=mapping, missing=missing, columns=[str(c) for c in df.columns])


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def parse_bool(value) -> Optional[bool]:
    if _is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Real):
        # XLSX numeric flags arrive as 1.0 / 0.0
        if math.isfinite(value) and value == int(value) and int(value) in (0, 1):
            return bool(int(value))
        return None
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


_THOUSANDS_COMMA = re.compile(r"^[+-]?\d{1,3}(,\d{3})+$")


def _normalise_number(text: str) -> str:
    """Locale-aware number normalisation: '1.200,5' / '1,200.5' / '1,200' / '1,5' / '72.5'."""
    text = re.sub(r"\s+", "", text)
    if "." in text and "," in text:
        decimal = "." if text.rfind(".") > text.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        return text.replace(thousands, "").replace(decimal, ".")
    if "," in text:
        return text.replace(",", "") if _THOUSANDS_COMMA.match(text) else text.replace(",", ".")
    return text


def _to_float(value) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        result = float(_normalise_number(str(value)))
    except (ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _to_int(value) -> Optional[int]:
    f = _to_float(value)
    return None if f is None else int(f)


def _text(value) -> str:
    return "" if _is_blank(value) else str(value).strip()


def parse_backlinks(df: pd.DataFrame, mapping: dict[str, str]) -> list[BrokenBacklink]:
    """Build BrokenBacklink rows. Rows missing url_from or url_to are dropped."""
    for field in REQUIRED_FIELDS:
        if field not in mapping:
            raise ValueError(f"Pflichtfeld nicht zugeordnet: {field}")

    def col(row, field):
        name = mapping.get(field)
        return row[name] if name is not None and name in row.index else None

    rows: list[BrokenBacklink] = []
    for _, row in df.iterrows():
        url_from, url_to = _text(col(row, "url_from")), _text(col(row, "url_to"))
        if not url_from or not url_to:
            continue
        dofollow = parse_bool(col(row, "is_dofollow"))
        if dofollow is None:
            nofollow = parse_bool(col(row, "is_nofollow"))
            dofollow = None if nofollow is None else not nofollow
        rows.append(
            BrokenBacklink(
                url_from=url_from,
                url_to=url_to,
                anchor=_text(col(row, "anchor")),
                snippet_left=_text(col(row, "snippet_left")),
                snippet_right=_text(col(row, "snippet_right")),
                title_from=_text(col(row, "title_from")),
                domain_rating=_to_float(col(row, "domain_rating")),
                url_rating=_to_float(col(row, "url_rating")),
                page_traffic=_to_int(col(row, "page_traffic")),
                is_dofollow=dofollow,
                is_content=parse_bool(col(row, "is_content")),
                http_code_target=_to_int(col(row, "http_code_target")),
            )
        )
    return rows
