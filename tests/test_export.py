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
    assert df.loc[1, "Content-Gap"] == "Ja"
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


def test_formula_injection_prevention():
    """Verify that formula injection is prevented by prefixing dangerous characters."""
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="=HYPERLINK(\"x\")", domain_rating=55.0, value_rank=1)
    r = MatchResult(bl, RecoveredContent(bl.url_to, "t", "wayback", snapshot_timestamp="20240315120000"), value_rank=1, priority=1)
    df = results_to_dataframe([r])
    # The dangerous anchor should start with ' to prevent formula evaluation
    assert df.loc[0, "Anker"].startswith("'=")


def test_formula_injection_xlsx_roundtrip():
    """Verify that formula injection is stored as string in XLSX and survives round-trip."""
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="=HYPERLINK(\"x\")", domain_rating=55.0, value_rank=1)
    r = MatchResult(bl, RecoveredContent(bl.url_to, "t", "wayback", snapshot_timestamp="20240315120000"), value_rank=1, priority=1)
    df = results_to_dataframe([r])
    data = to_xlsx_bytes(df)
    back = pd.read_excel(io.BytesIO(data))
    # Should be stored as string (starts with ')
    assert isinstance(back.loc[0, "Anker"], str)
    assert back.loc[0, "Anker"].startswith("'=")


def test_csv_decimal_separator():
    """Verify that CSV uses comma as decimal separator for German Excel."""
    df = results_to_dataframe(rows())
    data = to_csv_bytes(df)
    # Decode and check for comma decimal separator
    csv_str = data.decode("utf-8-sig")
    # Score 1 of 0.91 should appear as 0,91 in CSV
    assert "0,91" in csv_str
    # Check header line is semicolon-joined COLUMNS
    lines = csv_str.split("\n")
    assert lines[0] == ";".join(["Priorität", "Rang Linkwert", "Linkgebende URL", "DR", "UR", "Traffic", "Anker", "Tote URL",
                                  "Quelle Text", "Snapshot", "Vorschlag 1", "Score 1", "Vorschlag 2", "Score 2", "Vorschlag 3", "Score 3",
                                  "Content-Gap", "Verifikation", "Fehler"])


def test_content_gap_ja_nein():
    """Verify that Content-Gap column uses Ja/Nein strings instead of True/False."""
    df = results_to_dataframe(rows())
    # Row 0 is not a gap
    assert df.loc[0, "Content-Gap"] == "Nein"
    # Row 1 is a gap
    assert df.loc[1, "Content-Gap"] == "Ja"


def test_source_is_called_wayback_machine():
    df = results_to_dataframe(rows())
    assert df.loc[0, "Quelle Text"] == "Wayback Machine"


def test_hidden_columns_are_dropped_and_order_kept():
    from blm.export import MAIL_HIDDEN_COLUMNS
    assert MAIL_HIDDEN_COLUMNS == ("Priorität", "Rang Linkwert", "Traffic", "Content-Gap")
    df = results_to_dataframe(rows(), [True, False], ["2026-10", "2026-09"], hide=MAIL_HIDDEN_COLUMNS)
    assert list(df.columns) == ["Neu", "Erstmals erfasst", "Linkgebende URL", "DR", "UR", "Anker", "Tote URL",
                                "Quelle Text", "Snapshot", "Vorschlag 1", "Score 1", "Vorschlag 2", "Score 2",
                                "Vorschlag 3", "Score 3", "Verifikation", "Fehler"]
    assert df.loc[0, "Linkgebende URL"] == "https://a.de/p"


def test_content_gap_rows_can_be_left_out_with_aligned_flags():
    r, gap = rows()
    third = MatchResult(BrokenBacklink(url_from="https://d.de", url_to="https://c.de/z"),
                        RecoveredContent("https://c.de/z", "t", "wayback"), priority=3)
    third.top = [Match("https://me.de/3", 0.8)]
    df = results_to_dataframe([r, gap, third], [True, True, False], ["2026-10", "2026-10", "2026-09"],
                              skip_content_gaps=True)
    assert list(df["Linkgebende URL"]) == ["https://a.de/p", "https://d.de"]
    assert list(df["Neu"]) == ["Ja", "Nein"] and list(df["Erstmals erfasst"]) == ["2026-10", "2026-09"]
    assert len(results_to_dataframe([r, gap, third])) == 3
