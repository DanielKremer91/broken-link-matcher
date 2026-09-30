import json
from pathlib import Path

import httpx
import pytest
import respx

from blm.cache import JsonCache
from blm.models import BrokenBacklink
from blm.wayback import (
    CDX_URL,
    WaybackError,
    extract_text,
    fallback_text,
    latest_snapshot,
    recover_content,
    slug_words,
    snapshot_url,
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
