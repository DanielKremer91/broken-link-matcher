import json

import pytest

from blm.history import HistoryError, load_seen, mark_new, pair_key, record_reported, save_seen
from blm.models import BrokenBacklink, Match, MatchResult, RecoveredContent


def row(url_from, url_to, *, gap=False, top=True):
    bl = BrokenBacklink(url_from=url_from, url_to=url_to)
    r = MatchResult(backlink=bl, recovered=RecoveredContent(url_to=url_to, text=None, source="none"))
    if top:
        r.top = [Match("https://me.de/x", 0.4 if gap else 0.8)]
    r.is_content_gap = gap
    return r


def test_pair_key_normalises_scheme_www_slash_and_case():
    a = pair_key(row(" https://www.A.de/x/ ", "http://k.de/y\n").backlink)
    b = pair_key(row("http://a.de/x", "https://www.k.de/y/").backlink)
    assert a == b == "a.de/x|k.de/y"


def test_missing_file_means_nothing_seen(tmp_path):
    assert load_seen(tmp_path / "fehlt.json") == {}


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "sub" / "seen.json"
    seen = {"b|2": {"status": "gap", "since": "2026-10"}, "a|1": {"status": "match", "since": "2026-09"}}
    save_seen(path, seen)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert list(data["keys"]) == ["a|1", "b|2"] and "updated" in data
    assert load_seen(path) == seen


@pytest.mark.parametrize("content", ["{kaputt", json.dumps({"keys": "x"}), json.dumps({"keys": ["a|1"]}),
                                     json.dumps({"keys": {"a|1": {"status": "neu", "since": "2026-10"}}})])
def test_unusable_file_raises_history_error(tmp_path, content):
    path = tmp_path / "seen.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(HistoryError):
        load_seen(path)


def test_unseen_rows_are_new():
    rows = [row("https://a.de", "https://k.de/1"), row("https://b.de", "https://k.de/2")]
    seen = {"a.de|k.de/1": {"status": "match", "since": "2026-09"}}
    assert mark_new(rows, seen, "2026-10") == [False, True]


def test_rerun_in_same_month_reports_the_same_rows():
    rows = [row("https://a.de", "https://k.de/1")]
    seen = record_reported({}, rows, "2026-10")
    assert mark_new(rows, seen, "2026-10") == [True]
    assert mark_new(rows, seen, "2026-11") == [False]


def test_gap_that_becomes_a_match_is_new_again_once():
    gap = row("https://a.de", "https://k.de/1", gap=True)
    seen = record_reported({}, [gap], "2026-10")
    assert mark_new([gap], seen, "2026-11") == [False]
    match = row("https://a.de", "https://k.de/1")
    assert mark_new([match], seen, "2026-11") == [True]
    seen = record_reported(seen, [match], "2026-11")
    assert seen["a.de|k.de/1"] == {"status": "match", "since": "2026-11"}
    assert mark_new([match], seen, "2026-12") == [False]


def test_match_that_turns_into_gap_is_not_new_and_not_downgraded():
    seen = record_reported({}, [row("https://a.de", "https://k.de/1")], "2026-10")
    gap = row("https://a.de", "https://k.de/1", gap=True)
    assert mark_new([gap], seen, "2026-11") == [False]
    assert record_reported(seen, [gap], "2026-11")["a.de|k.de/1"]["status"] == "match"


def test_catch_up_of_earlier_month_shows_later_rows_as_new():
    rows = [row("https://a.de", "https://k.de/1")]
    seen = record_reported({}, rows, "2026-12")
    assert mark_new(rows, seen, "2026-11") == [True]


def test_rows_without_match_are_not_recorded():
    assert record_reported({}, [row("https://a.de", "https://k.de/1", top=False)], "2026-10") == {}


def test_rerun_keeps_row_even_if_status_flipped():
    seen = record_reported({}, [row("https://a.de", "https://k.de/1")], "2026-10")
    assert mark_new([row("https://a.de", "https://k.de/1", gap=True)], seen, "2026-10") == [True]
