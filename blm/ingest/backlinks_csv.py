"""Read a broken-backlinks table (Ahrefs UI export, Ahrefs API/MCP output, or any
other tool) and normalise it into BrokenBacklink objects.

Column detection is alias based. Extend FIELD_ALIASES to support more tools.
"""

from __future__ import annotations

import math
import numbers
import re
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from blm.ingest.tables import read_table  # noqa: F401  (re-exported for existing imports)
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


_MONTHS = {
    "jan": 1, "feb": 2, "mär": 3, "mrz": 3, "mar": 3, "apr": 4, "mai": 5, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "okt": 10, "oct": 10, "nov": 11, "dez": 12, "dec": 12,
}
# Excel shows "4.6" as a German date ("04. Jun"); "M.r" also covers "März" written in
# MacRoman and read back as UTF-8 with a replacement character.
_EXCEL_DATE_DE = re.compile(
    r"^(\d{1,2})\.\s?(Jan|Feb|Mär|Mrz|M.r|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)\.?$", re.IGNORECASE
)
_EXCEL_DATE_EN = re.compile(r"^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$", re.IGNORECASE)


def _excel_date_to_float(text: str) -> Optional[float]:
    match = _EXCEL_DATE_DE.match(text) or _EXCEL_DATE_EN.match(text)
    if match is None:
        return None
    day, month = match.groups()
    month_number = _MONTHS.get(month.lower(), 3)  # only "M?r" is not in the table: March
    return float(f"{int(day)}.{month_number}")


def _parse_float(value) -> tuple[Optional[float], bool]:
    """(number, repaired_from_excel_date)."""
    if _is_blank(value):
        return None, False
    text = str(value).strip()
    repaired = False
    try:
        result = float(_normalise_number(text))
    except (ValueError, OverflowError):
        result = _excel_date_to_float(text)
        if result is None:
            return None, False
        repaired = True
    return (result, repaired) if math.isfinite(result) else (None, False)


def _to_float(value) -> Optional[float]:
    return _parse_float(value)[0]


def _to_int(value) -> Optional[int]:
    f = _to_float(value)
    return None if f is None else int(f)


def _text(value) -> str:
    return "" if _is_blank(value) else str(value).strip()


def parse_backlinks(
    df: pd.DataFrame, mapping: dict[str, str], *, report: Optional[dict] = None
) -> list[BrokenBacklink]:
    """Build BrokenBacklink rows. Rows missing url_from or url_to are dropped.

    If `report` is given, report["excel_dates_repaired"] is increased by the number of
    numeric cells that Excel had turned into dates (e.g. "04. Jun" for 4.6).
    """
    for field in REQUIRED_FIELDS:
        if field not in mapping:
            raise ValueError(f"Pflichtfeld nicht zugeordnet: {field}")
    repaired = 0

    def col(row, field):
        name = mapping.get(field)
        return row[name] if name is not None and name in row.index else None

    def number(row, field) -> Optional[float]:
        nonlocal repaired
        value, was_date = _parse_float(col(row, field))
        repaired += was_date
        return value

    def integer(row, field) -> Optional[int]:
        value = number(row, field)
        return None if value is None else int(value)

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
                domain_rating=number(row, "domain_rating"),
                url_rating=number(row, "url_rating"),
                page_traffic=integer(row, "page_traffic"),
                is_dofollow=dofollow,
                is_content=parse_bool(col(row, "is_content")),
                http_code_target=integer(row, "http_code_target"),
            )
        )
    if report is not None:
        report["excel_dates_repaired"] = report.get("excel_dates_repaired", 0) + repaired
    return rows
