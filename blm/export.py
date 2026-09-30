"""Turn MatchResult rows into a DataFrame and downloadable files."""

from __future__ import annotations

import io
from typing import Optional

import pandas as pd

from blm.models import MatchResult

COLUMNS = [
    "Priorität", "Rang Linkwert", "Linkgebende URL", "DR", "UR", "Traffic", "Anker", "Tote URL",
    "Quelle Text", "Snapshot", "Vorschlag 1", "Score 1", "Vorschlag 2", "Score 2", "Vorschlag 3", "Score 3",
    "Content-Gap", "Verifikation", "Fehler",
]


def format_snapshot(ts: Optional[str]) -> str:
    if not ts or len(ts) < 8:
        return ""
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"


def results_to_dataframe(results: list[MatchResult]) -> pd.DataFrame:
    records = []
    for r in results:
        top = r.top + [None] * (3 - len(r.top))
        rec = {
            "Priorität": r.priority,
            "Rang Linkwert": r.value_rank,
            "Linkgebende URL": r.backlink.url_from,
            "DR": r.backlink.domain_rating,
            "UR": r.backlink.url_rating,
            "Traffic": r.backlink.page_traffic,
            "Anker": r.backlink.anchor,
            "Tote URL": r.backlink.url_to,
            "Quelle Text": r.recovered.source,
            "Snapshot": format_snapshot(r.recovered.snapshot_timestamp),
        }
        for i, m in enumerate(top, start=1):
            rec[f"Vorschlag {i}"] = m.url if m else ""
            rec[f"Score {i}"] = round(m.score, 3) if m else None
        rec["Content-Gap"] = r.is_content_gap
        rec["Verifikation"] = r.verification
        rec["Fehler"] = " | ".join(r.errors)
        records.append(rec)
    return pd.DataFrame.from_records(records, columns=COLUMNS)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Treffer")
    return buf.getvalue()
