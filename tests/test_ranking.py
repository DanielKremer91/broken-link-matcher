from blm.models import BrokenBacklink
from blm.ranking import SORT_FIELDS, rank_backlinks


def bl(i, dr=None, ur=None, traffic=None, dofollow=None, content=None):
    return BrokenBacklink(
        url_from=f"https://s{i}.de/p", url_to=f"https://c.de/{i}", domain_rating=dr,
        url_rating=ur, page_traffic=traffic, is_dofollow=dofollow, is_content=content,
    )


def test_sorts_by_dr_then_traffic_with_none_last():
    rows = [bl(1, dr=50, traffic=10), bl(2, dr=70, traffic=1), bl(3, dr=None, traffic=999), bl(4, dr=70, traffic=500)]
    out = rank_backlinks(rows, dofollow_only=False, content_only=False)
    assert [r.url_to for r in out] == ["https://c.de/4", "https://c.de/2", "https://c.de/1", "https://c.de/3"]
    assert [r.value_rank for r in out] == [1, 2, 3, 4]


def test_filters_dofollow_and_content_but_keeps_none():
    rows = [bl(1, dofollow=False, content=True), bl(2, dofollow=True, content=False), bl(3, dofollow=None, content=None), bl(4, dofollow=True, content=True)]
    out = rank_backlinks(rows)
    assert sorted(r.url_to for r in out) == ["https://c.de/3", "https://c.de/4"]


def test_min_dr_drops_low_but_keeps_unknown():
    rows = [bl(1, dr=20), bl(2, dr=60), bl(3, dr=None)]
    out = rank_backlinks(rows, dofollow_only=False, content_only=False, min_dr=50)
    assert sorted(r.url_to for r in out) == ["https://c.de/2", "https://c.de/3"]


def test_sort_by_traffic_and_limit():
    rows = [bl(1, dr=90, traffic=5), bl(2, dr=10, traffic=500), bl(3, dr=50, traffic=100)]
    out = rank_backlinks(rows, dofollow_only=False, content_only=False, sort_by="page_traffic", limit=2)
    assert [r.url_to for r in out] == ["https://c.de/2", "https://c.de/3"]


def test_does_not_mutate_input():
    rows = [bl(1, dr=1)]
    rank_backlinks(rows, dofollow_only=False, content_only=False)
    assert rows[0].value_rank is None


def test_sort_fields_constant():
    assert SORT_FIELDS == ("domain_rating", "url_rating", "page_traffic")
