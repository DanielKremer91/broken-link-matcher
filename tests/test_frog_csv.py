from pathlib import Path

import numpy as np
import pytest

from blm.ingest.frog_csv import load_frog_embeddings

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
