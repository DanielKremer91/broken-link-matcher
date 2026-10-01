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


@pytest.mark.parametrize(
    "value,expected",
    [("1,200", 1200.0), ("1.200,5", 1200.5), ("1,200.5", 1200.5), ("72.5", 72.5),
     ("1,5", 1.5), ("1 200", 1200.0), ("72", 72.0), ("abc", None), ("", None)],
)
def test_number_parsing_is_locale_aware(value, expected):
    from blm.ingest.backlinks_csv import _to_float

    assert _to_float(value) == expected


def test_thousands_separator_in_int_column():
    from blm.ingest.backlinks_csv import _to_int

    assert _to_int("1,200") == 1200
    assert _to_int("1.200,5") == 1200


@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf", "Infinity"])
def test_non_finite_numbers_become_none(value):
    from blm.ingest.backlinks_csv import _to_float, _to_int

    assert _to_float(value) is None
    assert _to_int(value) is None


def test_row_with_non_finite_cell_still_imports(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("url_from,url_to,traffic,domain_rating_source\nhttps://a.de,https://b.de,nan,inf\n", encoding="utf-8")
    df = read_table(p)
    rows = parse_backlinks(df, detect_columns(df).mapping)
    assert len(rows) == 1
    assert rows[0].page_traffic is None
    assert rows[0].domain_rating is None


@pytest.mark.parametrize("value,expected", [(1.0, True), (0.0, False), (1, True), (0, False), (2.0, None), (0.5, None),
                                            (float("inf"), None), ("1.0", True), ("0.0", False)])
def test_parse_bool_numeric_values(value, expected):
    assert parse_bool(value) is expected


def test_xlsx_numeric_nofollow_flags(tmp_path):
    import pandas as pd

    p = tmp_path / "flags.xlsx"
    pd.DataFrame(
        {
            "Referring page URL": ["https://a.de", "https://c.de"],
            "Target URL": ["https://b.de/x", "https://b.de/y"],
            "Nofollow": [1.0, None],
        }
    ).to_excel(p, index=False)
    df = read_table(p)
    rows = parse_backlinks(df, detect_columns(df).mapping)
    assert rows[0].is_dofollow is False
    assert rows[1].is_dofollow is None


def test_read_utf16_tab_separated_ahrefs_export(tmp_path):
    content = (FIX / "ahrefs_ui_export.csv").read_text(encoding="utf-8").replace(",", "\t")
    p = tmp_path / "ahrefs.csv"
    p.write_bytes(content.encode("utf-16"))
    df = read_table(p)
    cm = detect_columns(df)
    assert cm.missing == []
    rows = parse_backlinks(df, cm.mapping)
    assert len(rows) == 2
    assert rows[0].anchor == "Ratgeber zu Stahlküchen"


def test_read_cp1252_file(tmp_path):
    p = tmp_path / "latin.csv"
    p.write_bytes("url_from;url_to;anchor\nhttps://a.de;https://b.de;Küche\n".encode("cp1252"))
    df = read_table(p)
    assert df["anchor"][0] == "Küche"


def test_single_column_file_is_not_split_on_underscore(tmp_path):
    p = tmp_path / "single.csv"
    p.write_text("url_from\nhttps://a.de\nhttps://b.de\n", encoding="utf-8")
    df = read_table(p)
    assert list(df.columns) == ["url_from"]
    assert len(df) == 2


def test_empty_file_raises_german_value_error(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    with pytest.raises(ValueError, match="Datei konnte nicht gelesen werden"):
        read_table(p)


def test_read_table_accepts_binary_stream():
    import io

    stream = io.BytesIO("url_from,url_to\nhttps://a.de,https://b.de\n".encode("utf-8"))
    df = read_table(stream, filename="upload.csv")
    assert list(df.columns) == ["url_from", "url_to"]


def test_mixed_encoding_file_is_read_with_replacement(tmp_path):
    """Excel on macOS re-saves mostly UTF-8 text but writes its own date strings in MacRoman."""
    p = tmp_path / "mixed.csv"
    p.write_bytes("url_from;url_to;title\nhttps://a.de;https://b.de/x;Küche – ".encode("utf-8") + b"M\x8arz\n")
    df = read_table(p)
    assert list(df.columns) == ["url_from", "url_to", "title"]
    assert df.loc[0, "url_to"] == "https://b.de/x"
    assert df.loc[0, "title"].startswith("Küche – M")


# ------------------------------------------------------------------ Excel turned decimals into dates
@pytest.mark.parametrize(
    "value,expected",
    [("04. Jun", 4.6), ("03. M�r", 3.3), ("03. Mär", 3.3), ("03. Mrz", 3.3), ("01. Jan", 1.1),
     ("4.Jun", 4.6), ("12. Dez.", 12.12), ("01. okt", 1.1), ("4-Jun", 4.6), ("1-Jan", 1.1), ("31-Dec", 31.12),
     ("2026-06-04 00:00:00", 4.6), ("2026-01-01", 1.1), ("2026-12-31", 31.12),
     ("2026-06-04 12:30:00", None), ("04. Juni", None), ("4-Juni", None), ("Jun", None)],
)
def test_excel_date_strings_are_turned_back_into_decimals(value, expected):
    from blm.ingest.backlinks_csv import _to_float

    assert _to_float(value) == expected


def test_excel_damaged_fixture_reports_repairs():
    df = read_table(FIX / "excel_damaged_backlinks.csv")
    report: dict = {}
    rows = parse_backlinks(df, detect_columns(df).mapping, report=report)
    assert [r.domain_rating for r in rows] == [4.6, 3.3, 72.0]
    assert [r.url_rating for r in rows] == [12.0, 1.1, 1.1]
    assert [r.page_traffic for r in rows] == [1200, None, 5]
    assert rows[2].anchor == "Größe"
    assert report == {"excel_dates_repaired": 4}


def test_report_accumulates_and_is_optional():
    df = read_table(FIX / "ahrefs_ui_export.csv")
    report = {"excel_dates_repaired": 2}
    parse_backlinks(df, detect_columns(df).mapping, report=report)
    assert report == {"excel_dates_repaired": 2}
    assert len(parse_backlinks(df, detect_columns(df).mapping)) == 2


def test_xlsx_datetime_cells_are_repaired_and_counted(tmp_path):
    import datetime as dt

    import pandas as pd

    p = tmp_path / "dates.xlsx"
    pd.DataFrame({"Referring page URL": ["https://a.de", "https://c.de"], "Target URL": ["https://b.de/x", "https://b.de/y"],
                  "Domain rating": [dt.datetime(2026, 6, 4), 72]}).to_excel(p, index=False)
    df = read_table(p)
    report: dict = {}
    rows = parse_backlinks(df, detect_columns(df).mapping, report=report)
    assert [r.domain_rating for r in rows] == [4.6, 72.0]
    assert report == {"excel_dates_repaired": 1}
