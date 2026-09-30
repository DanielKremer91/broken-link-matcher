from pathlib import Path

import httpx
import pytest
import respx

from blm.models import BrokenBacklink, MatchResult, RecoveredContent
from blm.verify import MAX_HTML_BYTES, canonical, verify_backlink, verify_results

FIX = Path(__file__).parent / "fixtures"
WITH = (FIX / "referring_with_link.html").read_text()
WITHOUT = (FIX / "referring_without_link.html").read_text()
FROM = "https://blog.example/kueche"
DEAD = "https://konkurrent.de/ratgeber/stahl"


def bl():
    return BrokenBacklink(url_from=FROM, url_to=DEAD)


def test_canonical():
    assert canonical("HTTPS://Konkurrent.de/ratgeber/stahl/#x") == "konkurrent.de/ratgeber/stahl"
    assert canonical("http://konkurrent.de/ratgeber/stahl") == canonical(DEAD)


@respx.mock
def test_confirmed_when_404_and_link_present():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, html=WITH))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


@respx.mock
def test_fixed_when_target_alive():
    respx.get(DEAD).mock(return_value=httpx.Response(200, text="ok"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_fixed_when_link_removed():
    respx.get(DEAD).mock(return_value=httpx.Response(410))
    respx.get(FROM).mock(return_value=httpx.Response(200, html=WITHOUT))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_unknown_on_timeout():
    respx.get(DEAD).mock(side_effect=httpx.ConnectTimeout("slow"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "unknown"


@respx.mock
def test_verify_results_sets_field_and_pauses_between_domains():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, html=WITH))
    respx.get("https://other.example/p").mock(return_value=httpx.Response(200, html=WITH))
    rows = [
        MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback")),
        MatchResult(BrokenBacklink(url_from="https://other.example/p", url_to=DEAD), RecoveredContent(DEAD, "t", "wayback")),
    ]
    pauses = []
    seen = []
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=pauses.append, progress=lambda i, n: seen.append((i, n)))
    assert [r.verification for r in rows] == ["confirmed", "confirmed"]
    assert pauses == [0.5]
    assert seen == [(1, 2), (2, 2)]


@pytest.mark.parametrize("status", [403, 429, 500, 503])
@respx.mock
def test_unknown_when_target_status_is_not_conclusive(status):
    respx.get(DEAD).mock(return_value=httpx.Response(status))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "unknown"


@respx.mock
def test_fixed_when_target_redirects_to_live_page():
    respx.get(DEAD).mock(return_value=httpx.Response(301, headers={"Location": DEAD + "-new"}))
    respx.get(DEAD + "-new").mock(return_value=httpx.Response(200, text="ok"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_link_resolved_against_final_url_after_redirect():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get("https://blog.example/p").mock(
        return_value=httpx.Response(301, headers={"Location": "https://mirror.example/p"})
    )
    respx.get("https://mirror.example/p").mock(
        return_value=httpx.Response(200, html='<a href="//konkurrent.de/ratgeber/stahl">x</a>')
    )
    with httpx.Client() as c:
        result = verify_backlink(BrokenBacklink(url_from="https://blog.example/p", url_to=DEAD), c)
    assert result == "confirmed"


@respx.mock
def test_base_href_is_respected():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    html = '<html><head><base href="https://konkurrent.de/"></head><body><a href="ratgeber/stahl">x</a></body></html>'
    respx.get(FROM).mock(return_value=httpx.Response(200, html=html))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


def test_canonical_strips_www_and_default_ports():
    assert canonical("https://www.Konkurrent.de:443/ratgeber/stahl/") == "konkurrent.de/ratgeber/stahl"
    assert canonical("http://konkurrent.de:80/ratgeber/stahl") == "konkurrent.de/ratgeber/stahl"
    assert canonical("https://konkurrent.de:8443/a") == "konkurrent.de:8443/a"
    assert canonical("https://konkurrent.de/a?x=1#f") == "konkurrent.de/a?x=1"


@respx.mock
def test_www_variant_of_link_counts_as_present():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    html = '<a href="https://www.konkurrent.de:443/ratgeber/stahl/">x</a>'
    respx.get(FROM).mock(return_value=httpx.Response(200, html=html))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


@respx.mock
def test_unknown_when_referring_page_is_not_html():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(
        return_value=httpx.Response(200, content=b"%PDF", headers={"Content-Type": "application/pdf"})
    )
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "unknown"


@respx.mock
def test_large_body_is_capped_but_early_link_is_found():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    head = '<html><body><a href="https://konkurrent.de/ratgeber/stahl">x</a><!--'
    body = head + "a" * (MAX_HTML_BYTES * 2)
    respx.get(FROM).mock(return_value=httpx.Response(200, html=body))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


@respx.mock
def test_target_status_is_fetched_once_per_run():
    target = respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, html=WITH))
    respx.get("https://other.example/p").mock(return_value=httpx.Response(200, html=WITH))
    rows = [
        MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback")),
        MatchResult(BrokenBacklink(url_from="https://other.example/p", url_to=DEAD), RecoveredContent(DEAD, "t", "wayback")),
    ]
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=lambda s: None)
    assert [r.verification for r in rows] == ["confirmed", "confirmed"]
    assert target.call_count == 1


@pytest.mark.parametrize("target", ["http://[::1", "https://xn--a.com/"])
@respx.mock
def test_malformed_target_url_is_unknown(target):
    with httpx.Client() as c:
        assert verify_backlink(BrokenBacklink(url_from=FROM, url_to=target), c) == "unknown"


@pytest.mark.parametrize("referring", ["http://[::1", "https://xn--a.com/"])
@respx.mock
def test_malformed_referring_url_is_unknown(referring):
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    with httpx.Client() as c:
        assert verify_backlink(BrokenBacklink(url_from=referring, url_to=DEAD), c) == "unknown"


@respx.mock
def test_malformed_href_on_referring_page_does_not_crash():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    html = '<a href="http://[::1">kaputt</a><a href="https://konkurrent.de/ratgeber/stahl">x</a>'
    respx.get(FROM).mock(return_value=httpx.Response(200, html=html))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


@respx.mock
def test_verify_results_marks_malformed_rows_unknown_and_continues():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, html=WITH))
    rows = [
        MatchResult(BrokenBacklink(url_from="http://[::1", url_to=DEAD), RecoveredContent(DEAD, "t", "wayback")),
        MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback")),
    ]
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=lambda s: None)
    assert [r.verification for r in rows] == ["unknown", "confirmed"]


def test_verify_results_last_resort_catches_unexpected_errors(monkeypatch):
    def explode(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("blm.verify.verify_backlink", explode)
    rows = [MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback"))]
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=lambda s: None)
    assert rows[0].verification == "unknown"


@respx.mock
def test_verify_sends_default_user_agent():
    from blm.wayback import USER_AGENT

    target = respx.get(DEAD).mock(return_value=httpx.Response(200, text="ok"))
    with httpx.Client() as c:
        verify_backlink(bl(), c)
    assert target.calls.last.request.headers["User-Agent"] == USER_AGENT


@respx.mock
def test_verify_results_sends_contact_user_agent():
    from blm.wayback import user_agent

    target = respx.get(DEAD).mock(return_value=httpx.Response(404))
    page = respx.get(FROM).mock(return_value=httpx.Response(200, html=WITH))
    rows = [MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback"))]
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=lambda s: None, user_agent=user_agent("seo@me.de"))
    assert rows[0].verification == "confirmed"
    assert "seo@me.de" in target.calls.last.request.headers["User-Agent"]
    assert "seo@me.de" in page.calls.last.request.headers["User-Agent"]
