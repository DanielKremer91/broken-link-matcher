import io
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from blm.ingest.frog_csv import FrogColumns, _parse_vector, detect_frog_columns, load_frog_embeddings
from blm.ingest.tables import TableInfo

FIX = Path(__file__).parent / "fixtures"


def test_wide_format_parses_urls_and_dimension():
    imp = load_frog_embeddings(FIX / "frog_wide.csv")
    assert imp.dimension == 4
    assert [p.url for p in imp.pages] == [
        "https://me.de/kueche-aus-stahl",
        "https://me.de/kochfeld-reinigen",
        "https://me.de/dunstabzug-tipps",
    ]
    assert imp.pages[0].vector.dtype == np.float32
    assert imp.pages[0].vector.tolist() == [1.0, 0.0, 0.0, 0.0]


def test_wide_format_skips_and_counts_broken_rows():
    imp = load_frog_embeddings(FIX / "frog_wide.csv")
    assert imp.skipped == 1


def test_single_column_format_with_titles():
    imp = load_frog_embeddings(FIX / "frog_single_column.csv")
    assert imp.dimension == 3
    assert imp.skipped == 1
    assert imp.pages[0].title == "Seite A"
    assert imp.pages[1].vector.tolist() == [0.0, 0.0, 1.0]


def test_missing_url_column_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("foo,embedding_0\nx,1.0\n")
    with pytest.raises(ValueError, match="URL"):
        load_frog_embeddings(f)


def test_no_vectors_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("url,other\nhttps://a.de,1\n")
    with pytest.raises(ValueError, match="Embedding"):
        load_frog_embeddings(f)


def test_wide_format_skips_empty_url(tmp_path):
    f = tmp_path / "empty_url.csv"
    f.write_text("url,embedding_0,embedding_1,embedding_2\nhttps://a.de,1.0,0.0,0.0\n,2.0,0.0,0.0\nhttps://c.de,0.0,1.0,0.0\n")
    imp = load_frog_embeddings(f)
    assert len(imp.pages) == 2
    assert [p.url for p in imp.pages] == ["https://a.de", "https://c.de"]
    assert imp.skipped == 1


def test_non_finite_vectors_skipped(tmp_path):
    f = tmp_path / "non_finite.csv"
    # Wide format with inf, single-column format with nan
    f.write_text("url,embedding_0,embedding_1\nhttps://a.de,1.0,inf\nhttps://b.de,1.0,0.5\n")
    imp = load_frog_embeddings(f)
    assert len(imp.pages) == 1
    assert imp.pages[0].url == "https://b.de"
    assert imp.skipped == 1


def test_single_column_detected_by_substring_in_header(tmp_path):
    """Screaming Frog UI exports name the column after the extractor, e.g. 'Embeddings Fressnapf 1'."""
    f = tmp_path / "ui_export.csv"
    f.write_text(
        '﻿"Address","Content Type","Status Code","Status","Embeddings Fressnapf 1"\n'
        '"https://me.de/a","text/html","200","","0.1,0.2,0.3"\n'
        '"https://me.de/b","text/html","200","","0.0,1.0,0.0"\n'
    )
    imp = load_frog_embeddings(f)
    assert imp.dimension == 3 and [p.url for p in imp.pages] == ["https://me.de/a", "https://me.de/b"]


def test_substring_match_prefers_exact_candidate_and_skips_url_column(tmp_path):
    f = tmp_path / "two.csv"
    f.write_text("Address,Embedding Model,Embeddings\nhttps://me.de/a,text-embedding-3-small,\"1,0\"\n")
    imp = load_frog_embeddings(f)
    assert imp.dimension == 2


# ------------------------------------------------------------------ shared reader, mapping, separators


def test_xlsx_frog_export(tmp_path):
    p = tmp_path / "frog.xlsx"
    pd.DataFrame({"Address": ["https://me.de/a", "https://me.de/b"],
                  "Embeddings X 1": ["0.1,0.2,0.3", "0.0,1.0,0.0"]}).to_excel(p, index=False)
    imp = load_frog_embeddings(p)
    assert imp.dimension == 3 and [p.url for p in imp.pages] == ["https://me.de/a", "https://me.de/b"]
    assert imp.table is not None and imp.table.kind == "xlsx"


def test_xlsx_wide_frog_export_with_numeric_cells_and_blank_row(tmp_path):
    p = tmp_path / "wide.xlsx"
    pd.DataFrame({"url": ["https://me.de/a", "https://me.de/b"],
                  "embedding_0": [1.0, None], "embedding_1": [0.5, 0.25]}).to_excel(p, index=False)
    imp = load_frog_embeddings(p)
    assert [p.url for p in imp.pages] == ["https://me.de/a"]
    assert imp.pages[0].vector.tolist() == [1.0, 0.5]
    assert imp.skipped == 1


def test_semicolon_frog_export_with_mixed_encoding(tmp_path):
    p = tmp_path / "frog.csv"
    p.write_bytes(
        "﻿Address;Title 1;Embeddings\n".encode("utf-8")
        + "https://me.de/küche;Küche Größe Übung;\"0.1,0.2,0.3\"\n".encode("utf-8")
        + b"https://me.de/m;M\x8arz;\"0.3,0.2,0.1\"\n"
    )
    imp = load_frog_embeddings(p)
    assert imp.dimension == 3
    assert [p.url for p in imp.pages] == ["https://me.de/küche", "https://me.de/m"]
    assert imp.table == TableInfo(";", "utf-8 (mit Ersatzzeichen)", "csv", 2, ["Address", "Title 1", "Embeddings"])


def test_stream_with_filename_attribute():
    stream = io.BytesIO(b"url,embedding_0,embedding_1\nhttps://me.de/a,1,0\n")
    stream.name = "upload.csv"
    assert load_frog_embeddings(stream).dimension == 2


def test_detect_frog_columns_single_and_wide():
    single = pd.DataFrame(columns=["Address", "Content Type", "Embeddings Fressnapf 1"])
    assert detect_frog_columns(single) == FrogColumns(
        url_col="Address", vector_col="Embeddings Fressnapf 1", wide=False,
        columns=["Address", "Content Type", "Embeddings Fressnapf 1"])
    wide = pd.DataFrame(columns=["url", "embedding_0", "embedding_1"])
    cols = detect_frog_columns(wide)
    assert cols.url_col == "url" and cols.wide is True and cols.vector_col is None
    unknown = pd.DataFrame(columns=["Seite", "Zahlen"])
    assert detect_frog_columns(unknown) == FrogColumns(url_col=None, vector_col=None, wide=False, columns=["Seite", "Zahlen"])


def test_manual_columns_load_unknown_headers(tmp_path):
    f = tmp_path / "custom.csv"
    f.write_text('Seite,Zahlen\nhttps://me.de/a,"0.1,0.2"\nhttps://me.de/b,"0.2,0.1"\n')
    with pytest.raises(ValueError, match="Seite, Zahlen"):
        load_frog_embeddings(f)
    imp = load_frog_embeddings(f, url_col="Seite", vector_col="Zahlen")
    assert imp.dimension == 2 and len(imp.pages) == 2


def test_manual_vector_col_wins_over_wide_columns(tmp_path):
    f = tmp_path / "both.csv"
    f.write_text('url,embedding_0,embedding_1,Vektor neu\nhttps://me.de/a,1,0,"0.1,0.2,0.3"\n')
    imp = load_frog_embeddings(f, vector_col="Vektor neu")
    assert imp.dimension == 3


def test_manual_url_col_wins_over_detected(tmp_path):
    f = tmp_path / "two_urls.csv"
    f.write_text('Address,Canonical,Embeddings\nhttps://me.de/a?x=1,https://me.de/a,"1,0"\n')
    imp = load_frog_embeddings(f, url_col="Canonical")
    assert imp.pages[0].url == "https://me.de/a"


def test_manual_columns_must_exist_and_differ(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text('Address,Embeddings\nhttps://me.de/a,"1,0"\n')
    with pytest.raises(ValueError, match="Address, Embeddings"):
        load_frog_embeddings(f, url_col="Nope")
    with pytest.raises(ValueError, match="verschieden"):
        load_frog_embeddings(f, url_col="Embeddings", vector_col="Embeddings")


def test_missing_vectors_error_lists_found_columns(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("url,other\nhttps://a.de,1\n")
    with pytest.raises(ValueError, match="Gefundene Spalten: url, other"):
        load_frog_embeddings(f)


@pytest.mark.parametrize(
    "raw,expected",
    [("0.1,0.2,0.3", [0.1, 0.2, 0.3]),
     ("0,1;0,2;0,3", [0.1, 0.2, 0.3]),
     ("0.1;0.2;0.3", [0.1, 0.2, 0.3]),
     ("[0.1, 0.2]", [0.1, 0.2]),
     ("-1e-3 2.5", [-0.001, 2.5]),
     ("", None), ("abc", None), ("0.1,,x", None)],
)
def test_parse_vector_separators(raw, expected):
    vec = _parse_vector(raw)
    if expected is None:
        assert vec is None
    else:
        assert vec.tolist() == pytest.approx(expected)


def test_excel_truncated_cell_is_skipped_by_majority_dimension(tmp_path):
    """Excel cuts cells at 32767 characters; such a row has fewer values than the rest."""
    full = ",".join(["0.1"] * 8)
    truncated = ",".join(["0.1"] * 5) + ",0."
    f = tmp_path / "trunc.csv"
    f.write_text(
        "Address,Embeddings\n"
        f'https://me.de/cut,"{truncated}"\n'
        f'https://me.de/a,"{full}"\n'
        f'https://me.de/b,"{full}"\n'
    )
    imp = load_frog_embeddings(f)
    assert imp.dimension == 8
    assert [p.url for p in imp.pages] == ["https://me.de/a", "https://me.de/b"]
    assert imp.skipped == 1


def test_tie_between_lengths_prefers_the_longer_vector(tmp_path):
    f = tmp_path / "tie.csv"
    f.write_text('Address,Embeddings\nhttps://me.de/cut,"0.1,0.2"\nhttps://me.de/full,"0.1,0.2,0.3"\n')
    imp = load_frog_embeddings(f)
    assert imp.dimension == 3 and [p.url for p in imp.pages] == ["https://me.de/full"]
    assert imp.skipped == 1


def test_wide_columns_with_decimal_commas(tmp_path):
    f = tmp_path / "wide_de.csv"
    f.write_text("url;embedding_0;embedding_1\nhttps://me.de/a;0,1;0,25\nhttps://me.de/b;1;0\n", encoding="utf-8")
    imp = load_frog_embeddings(f)
    assert imp.dimension == 2 and imp.skipped == 0
    assert imp.pages[0].vector.tolist() == pytest.approx([0.1, 0.25])


def test_vector_column_found_by_content_when_name_is_generic(tmp_path):
    vec = ",".join(str(i / 100) for i in range(64))
    p = tmp_path / "customjs.ndjson"
    p.write_text(
        f'{{"Address":"https://a.de/1","Content Type":"text/html","BORA MC Extraction 1":"{vec}"}}\n'
        f'{{"Address":"https://a.de/2","Content Type":"text/html","BORA MC Extraction 1":"{vec}"}}\n',
        encoding="utf-8")
    imp = load_frog_embeddings(p)
    assert imp.dimension == 64 and len(imp.pages) == 2
    from blm.ingest.tables import read_table
    assert detect_frog_columns(read_table(p)).vector_col == "BORA MC Extraction 1"


def test_content_detection_tolerates_a_few_error_cells(tmp_path):
    vec = ",".join(str(i / 100) for i in range(64))
    rows = [f'{{"Address":"https://a.de/{i}","Ext 1":"{"rate limit" if i == 0 else vec}"}}' for i in range(5)]
    p = tmp_path / "x.ndjson"
    p.write_text("\n".join(rows), encoding="utf-8")
    imp = load_frog_embeddings(p)
    assert len(imp.pages) == 4 and imp.skipped == 1


def test_short_numeric_columns_are_not_vectors(tmp_path):
    import pytest
    p = tmp_path / "x.csv"
    p.write_text("Address,Status Code,Werte\nhttps://a.de,200,\"1,2,3\"\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Keine Embedding-Spalten"):
        load_frog_embeddings(p)
