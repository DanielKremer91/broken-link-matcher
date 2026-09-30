import numpy as np

from blm.models import BrokenBacklink, Match, MatchResult, OwnPage, RecoveredContent


def test_broken_backlink_defaults():
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://b.de/dead")
    assert bl.anchor == ""
    assert bl.domain_rating is None
    assert bl.is_dofollow is None
    assert bl.value_rank is None


def test_match_result_defaults():
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://b.de/dead")
    rc = RecoveredContent(url_to=bl.url_to, text=None, source="none")
    mr = MatchResult(backlink=bl, recovered=rc)
    assert mr.top == []
    assert mr.is_content_gap is False
    assert mr.verification == "skipped"
    assert mr.errors == []


def test_own_page_holds_vector():
    p = OwnPage(url="https://me.de/x", vector=np.zeros(3, dtype=np.float32))
    assert p.vector.shape == (3,)
    assert p.title == ""
