from pathlib import Path

import pytest

from blm.ingest.backlinks_csv import (
    REQUIRED_FIELDS,
    detect_columns,
    parse_backlinks,
    parse_bool,
    read_table,
)

FIX = Path(__file__).parent / "fixtures"


def test_detects_ahrefs_ui_columns():
    df = read_table(FIX / "ahrefs_ui_export.csv")
    cm = detect_columns(df)
    assert cm.missing == []
    assert cm.mapping["url_from"] == "Referring page URL"
    assert cm.mapping["url_to"] == "Target URL"
    assert cm.mapping["domain_rating"] == "Domain rating"
    assert cm.mapping["is_nofollow"] == "Nofollow"


def test_parses_ahrefs_ui_rows():
    df = read_table(FIX / "ahrefs_ui_export.csv")
    rows = parse_backlinks(df, detect_columns(df).mapping)
    assert len(rows) == 2
    r = rows[0]
    assert r.url_from == "https://blog.example/kueche"
    assert r.anchor == "Ratgeber zu Stahlküchen"
    assert r.domain_rating == 72.0
    assert r.page_traffic == 1200
    assert r.is_dofollow is True
    assert r.is_content is True
    assert r.http_code_target == 404
    assert rows[1].is_dofollow is False
    assert rows[1].page_traffic is None


def test_parses_ahrefs_api_schema():
    df = read_table(FIX / "ahrefs_api_export.csv")
    cm = detect_columns(df)
    assert cm.missing == []
    rows = parse_backlinks(df, cm.mapping)
    assert rows[0].title_from == "Beste Küchentipps"
    assert rows[0].is_dofollow is True
    assert rows[0].url_rating == 35.0


def test_unknown_columns_reports_missing_and_lists_columns():
    df = read_table(FIX / "unknown_columns.csv")
    cm = detect_columns(df)
    assert set(cm.missing) == set(REQUIRED_FIELDS)
    assert cm.columns == ["Quelle", "Ziel", "Text"]


def test_manual_mapping_works():
    df = read_table(FIX / "unknown_columns.csv")
    rows = parse_backlinks(df, {"url_from": "Quelle", "url_to": "Ziel", "anchor": "Text"})
    assert rows[0].url_to == "https://y.de/b"
    assert rows[0].anchor == "hallo"
    assert rows[0].domain_rating is None


def test_rows_without_urls_are_dropped():
    df = read_table(FIX / "unknown_columns.csv")
    df.loc[len(df)] = ["", "https://y.de/c", "x"]
    rows = parse_backlinks(df, {"url_from": "Quelle", "url_to": "Ziel"})
    assert len(rows) == 1


@pytest.mark.parametrize(
    "value,expected",
    [("Yes", True), ("ja", True), ("true", True), ("1", True), ("dofollow", True),
     ("No", False), ("nein", False), ("false", False), ("0", False), ("nofollow", False),
     ("", None), (None, None), (float("nan"), None), ("maybe", None)],
)
def test_parse_bool(value, expected):
    assert parse_bool(value) is expected


def test_read_xlsx(tmp_path):
    import pandas as pd

    p = tmp_path / "x.xlsx"
    pd.DataFrame({"Referring page URL": ["https://a.de"], "Target URL": ["https://b.de/x"]}).to_excel(p, index=False)
    df = read_table(p)
    assert list(df.columns) == ["Referring page URL", "Target URL"]
