import json

import pytest

from blm.history import HistoryError, load_seen, mark_new, pair_key, save_seen
from blm.models import BrokenBacklink, MatchResult, RecoveredContent


def row(url_from, url_to):
    bl = BrokenBacklink(url_from=url_from, url_to=url_to)
    return MatchResult(backlink=bl, recovered=RecoveredContent(url_to=url_to, text=None, source="none"))


def test_pair_key_ignores_surrounding_whitespace():
    assert pair_key(row(" https://a.de/x ", "https://k.de/y\n").backlink) == "https://a.de/x|https://k.de/y"


def test_missing_file_means_nothing_seen(tmp_path):
    assert load_seen(tmp_path / "fehlt.json") == set()


def test_save_and_load_roundtrip_sorted(tmp_path):
    path = tmp_path / "sub" / "seen.json"
    save_seen(path, {"b|2", "a|1"})
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["keys"] == ["a|1", "b|2"] and "updated" in data
    assert load_seen(path) == {"a|1", "b|2"}


def test_corrupt_file_raises_history_error(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text("{kaputt", encoding="utf-8")
    with pytest.raises(HistoryError):
        load_seen(path)


def test_wrong_shape_raises_history_error(tmp_path):
    path = tmp_path / "seen.json"
    path.write_text(json.dumps({"keys": "nicht-liste"}), encoding="utf-8")
    with pytest.raises(HistoryError):
        load_seen(path)


def test_mark_new_flags_unseen_rows_only():
    rows = [row("https://a.de", "https://k.de/1"), row("https://b.de", "https://k.de/2")]
    assert mark_new(rows, {"https://a.de|https://k.de/1"}) == [False, True]
