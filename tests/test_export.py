import io

import pandas as pd

from blm.export import format_snapshot, results_to_dataframe, to_csv_bytes, to_xlsx_bytes
from blm.models import BrokenBacklink, Match, MatchResult, RecoveredContent


def rows():
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="Anker", domain_rating=55.0, value_rank=1)
    r = MatchResult(bl, RecoveredContent(bl.url_to, "t", "wayback", snapshot_timestamp="20240315120000"), value_rank=1, priority=1)
    r.top = [Match("https://me.de/1", 0.91), Match("https://me.de/2", 0.7)]
    r.verification = "confirmed"
    gap = MatchResult(BrokenBacklink(url_from="https://b.de", url_to="https://c.de/y", value_rank=2),
                      RecoveredContent("https://c.de/y", "t", "fallback", error="Kein Snapshot mit Status 200"),
                      is_content_gap=True, value_rank=2, priority=2)
    gap.errors = ["Kein Snapshot mit Status 200"]
    return [r, gap]


def test_format_snapshot():
    assert format_snapshot("20240315120000") == "2024-03-15"
    assert format_snapshot(None) == ""


def test_dataframe_columns_and_values():
    df = results_to_dataframe(rows())
    assert list(df.columns)[:4] == ["Priorität", "Rang Linkwert", "Linkgebende URL", "DR"]
    assert df.loc[0, "Vorschlag 1"] == "https://me.de/1"
    assert df.loc[0, "Score 1"] == 0.91
    assert df.loc[0, "Vorschlag 3"] == ""
    assert df.loc[0, "Snapshot"] == "2024-03-15"
    assert df.loc[1, "Quelle Text"] == "fallback"
    assert bool(df.loc[1, "Content-Gap"]) is True
    assert "Kein Snapshot" in df.loc[1, "Fehler"]


def test_csv_bytes_use_bom_and_semicolon():
    data = to_csv_bytes(results_to_dataframe(rows()))
    assert data.startswith("﻿".encode("utf-8"))
    assert b"Priorit" in data and b";" in data


def test_xlsx_roundtrip():
    data = to_xlsx_bytes(results_to_dataframe(rows()))
    back = pd.read_excel(io.BytesIO(data))
    assert len(back) == 2
    assert back.loc[0, "Linkgebende URL"] == "https://a.de/p"
