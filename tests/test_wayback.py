import json
from pathlib import Path

import httpx
import pytest
import respx

from blm.cache import JsonCache
from blm.models import BrokenBacklink
from blm.wayback import (
    CACHE_MAX_CHARS,
    CDX_URL,
    USER_AGENT,
    WaybackError,
    extract_text,
    fallback_text,
    latest_snapshot,
    recover_content,
    slug_words,
    snapshot_url,
    user_agent,
)

FIX = Path(__file__).parent / "fixtures"
CDX_HIT = json.loads((FIX / "cdx_hit.json").read_text())
HTML = (FIX / "archived_page.html").read_text()
DEAD = "https://konkurrent.de/ratgeber/stahl"


def no_sleep(_seconds):
    pass


def bl(**kw):
    base = dict(url_from="https://blog.example/kueche", url_to=DEAD)
    base.update(kw)
    return BrokenBacklink(**base)


def test_snapshot_url_uses_id_flag():
    assert snapshot_url("20240315120000", DEAD) == f"https://web.archive.org/web/20240315120000id_/{DEAD}"


@respx.mock
def test_latest_snapshot_requests_newest_200():
    route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    with httpx.Client() as client:
        ts, original = latest_snapshot(DEAD, client, sleeper=no_sleep)
    assert (ts, original) == ("20240315120000", DEAD)
    params = route.calls.last.request.url.params
    assert params["filter"] == "statuscode:200"
    assert params["limit"] == "-1"
    assert params["url"] == DEAD


@respx.mock
def test_latest_snapshot_none_when_no_rows():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[["timestamp", "original"]]))
    with httpx.Client() as client:
        assert latest_snapshot(DEAD, client, sleeper=no_sleep) is None


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(CDX_URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json=CDX_HIT)])
    with httpx.Client() as client:
        assert latest_snapshot(DEAD, client, sleeper=no_sleep) is not None
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_three_retries():
    respx.get(CDX_URL).mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(WaybackError):
        latest_snapshot(DEAD, client, sleeper=no_sleep)


def test_extract_text_returns_main_content_only():
    text = extract_text(HTML)
    assert "Edelstahl ist hygienisch" in text
    assert "Impressum" not in text


def test_slug_words():
    assert slug_words("https://konkurrent.de/ratgeber/stahl-kueche_pflege.html?x=1") == "ratgeber stahl kueche pflege"


def test_fallback_text_concatenates_existing_fields_only():
    text = fallback_text(bl(title_from="Beste Küchentipps", anchor="Ratgeber zu Stahlküchen", snippet_left="Wir empfehlen den", snippet_right="von Konkurrent."))
    assert text == "Beste Küchentipps. Ratgeber zu Stahlküchen. Wir empfehlen den. von Konkurrent. ratgeber stahl"


def test_fallback_text_none_when_nothing_available():
    assert fallback_text(BrokenBacklink(url_from="https://a.de", url_to="https://b.de/")) is None


@respx.mock
def test_recover_content_from_wayback_and_caches(tmp_path):
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    page = respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    cache = JsonCache(tmp_path)
    with httpx.Client() as client:
        rc = recover_content(bl(), client, cache, sleeper=no_sleep)
        assert rc.source == "wayback"
        assert rc.snapshot_timestamp == "20240315120000"
        assert "Edelstahl" in rc.text
        rc2 = recover_content(bl(), client, cache, sleeper=no_sleep)
    assert rc2.text == rc.text
    assert page.call_count == 1


@respx.mock
def test_recover_content_falls_back_when_unarchived():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[["timestamp", "original"]]))
    with httpx.Client() as client:
        rc = recover_content(bl(anchor="Stahlküchen Guide"), client, None, sleeper=no_sleep)
    assert rc.source == "fallback"
    assert rc.text == "Stahlküchen Guide. ratgeber stahl"
    assert rc.snapshot_timestamp is None


@respx.mock
def test_recover_content_none_when_unarchived_and_no_fields():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[]))
    with httpx.Client() as client:
        rc = recover_content(BrokenBacklink(url_from="https://a.de", url_to="https://b.de/"), client, None, sleeper=no_sleep)
    assert rc.source == "none"
    assert rc.text is None


@respx.mock
def test_recover_content_records_error_on_wayback_failure():
    respx.get(CDX_URL).mock(return_value=httpx.Response(500))
    with httpx.Client() as client:
        rc = recover_content(bl(anchor="x"), client, None, sleeper=no_sleep)
    assert rc.source == "fallback"
    assert "Wayback" in rc.error


@respx.mock
def test_text_is_capped():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    with httpx.Client() as client:
        rc = recover_content(bl(), client, None, max_chars=40, sleeper=no_sleep)
    assert len(rc.text) == 40


@respx.mock
def test_recover_content_falls_back_on_unparseable_cdx_payload():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, text="<html>busy</html>"))
    with httpx.Client() as client:
        rc = recover_content(bl(anchor="x"), client, None, sleeper=no_sleep)
    assert rc.source == "fallback"
    assert "Wayback" in rc.error


@respx.mock
def test_recover_content_decodes_latin1_snapshot_via_meta_charset():
    html = (
        '<html><head><meta charset="iso-8859-1"></head><body><main><h1>Küchen aus Edelstahl</h1>'
        "<p>Edelstahl ist hygienisch und langlebig. Fingerabdrücke lassen sich mit einem Tuch entfernen.</p>"
        "</main></body></html>"
    )
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, content=html.encode("latin-1")))
    with httpx.Client() as client:
        rc = recover_content(bl(), client, None, sleeper=no_sleep)
    assert rc.source == "wayback"
    assert "Küchen" in rc.text
    assert "Fingerabdrücke" in rc.text
    assert "�" not in rc.text


@respx.mock
def test_recover_content_falls_back_on_non_transport_request_error():
    respx.get(CDX_URL).mock(side_effect=httpx.TooManyRedirects("loop"))
    with httpx.Client() as client:
        rc = recover_content(bl(anchor="x"), client, None, sleeper=no_sleep)
    assert rc.source == "fallback"
    assert "Wayback" in rc.error


def cached_entry(text):
    return {"url_to": DEAD, "text": text, "source": "wayback", "snapshot_timestamp": "20240315120000", "error": None}


@respx.mock
def test_cache_hit_is_cut_to_max_chars(tmp_path):
    cache = JsonCache(tmp_path)
    cache.set("wayback", DEAD, cached_entry("x" * 1000))
    with httpx.Client() as client:
        rc = recover_content(bl(), client, cache, max_chars=100, sleeper=no_sleep)
    assert rc.source == "wayback" and rc.text == "x" * 100


@respx.mock
def test_fetch_caches_up_to_cache_max_chars_not_max_chars(tmp_path):
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    cache = JsonCache(tmp_path)
    with httpx.Client() as client:
        short = recover_content(bl(), client, cache, max_chars=40, sleeper=no_sleep)
        longer = recover_content(bl(), client, cache, max_chars=CACHE_MAX_CHARS, sleeper=no_sleep)
    assert len(short.text) == 40
    assert len(longer.text) > 40 and longer.text.startswith(short.text)
    assert len(cache.get("wayback", DEAD)["text"]) <= CACHE_MAX_CHARS


@pytest.mark.parametrize("entry", [{"foo": 1}, {"url_to": DEAD}, {**cached_entry("t"), "extra": 1}, cached_entry(5)])
@respx.mock
def test_malformed_cache_entry_is_refetched(tmp_path, entry):
    cdx = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    cache = JsonCache(tmp_path)
    cache.set("wayback", DEAD, entry)
    with httpx.Client() as client:
        rc = recover_content(bl(), client, cache, sleeper=no_sleep)
    assert cdx.call_count == 1
    assert rc.source == "wayback" and "Edelstahl" in rc.text


def test_user_agent_default_unchanged_and_contact_appended():
    assert user_agent() == USER_AGENT == user_agent(None) == user_agent("  ")
    ua = user_agent("seo@me.de")
    assert ua.startswith("broken-link-matcher/0.1 (") and "seo@me.de" in ua


def test_user_agent_strips_control_and_non_ascii_characters():
    ua = user_agent("a@b.de\r\nX-Evil: 1 müller")
    assert "\r" not in ua and "\n" not in ua
    ua.encode("ascii")


@respx.mock
def test_recover_content_sends_contact_user_agent():
    cdx = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    page = respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    with httpx.Client() as client:
        recover_content(bl(), client, None, sleeper=no_sleep, user_agent=user_agent("seo@me.de"))
    assert "seo@me.de" in cdx.calls.last.request.headers["User-Agent"]
    assert "seo@me.de" in page.calls.last.request.headers["User-Agent"]


@respx.mock
def test_recover_content_pauses_one_second_between_cdx_and_snapshot():
    events = []

    def cdx(request):
        events.append("cdx")
        return httpx.Response(200, json=CDX_HIT)

    def snap(request):
        events.append("snapshot")
        return httpx.Response(200, text=HTML)

    respx.get(CDX_URL).mock(side_effect=cdx)
    respx.get(snapshot_url("20240315120000", DEAD)).mock(side_effect=snap)
    with httpx.Client() as client:
        recover_content(bl(), client, None, sleeper=lambda s: events.append(s))
    assert events == ["cdx", 1.0, "snapshot"]


@respx.mock
def test_recover_content_does_not_pause_without_snapshot_request():
    slept = []
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[["timestamp", "original"]]))
    with httpx.Client() as client:
        recover_content(bl(anchor="x"), client, None, sleeper=slept.append)
    assert slept == []


def test_fallback_content_builds_per_backlink_result():
    from blm.wayback import fallback_content

    rc = fallback_content(bl(anchor="Stahlküchen Guide"), "Kein Snapshot mit Status 200", max_chars=10)
    assert (rc.source, rc.text, rc.error) == ("fallback", "Stahlküche", "Kein Snapshot mit Status 200")
    none = fallback_content(BrokenBacklink(url_from="https://a.de", url_to="https://b.de/"), "x")
    assert (none.source, none.text) == ("none", None)
