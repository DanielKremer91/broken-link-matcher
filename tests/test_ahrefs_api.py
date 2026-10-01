import json
from pathlib import Path

import httpx
import pytest
import respx

from blm.ingest.ahrefs_api import AHREFS_URL, AhrefsError, describe_filters, fetch_broken_backlinks

FIX = Path(__file__).parent / "fixtures"
RESPONSE = json.loads((FIX / "ahrefs_api_response.json").read_text())


@respx.mock
def test_fetch_maps_fields_and_flags_from_response():
    route = respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=RESPONSE))
    rows = fetch_broken_backlinks("tok", "konkurrent.de", limit=50)
    assert len(rows) == 2
    assert rows[0].title_from == "Beste Küchentipps"
    assert rows[0].domain_rating == 72.0
    assert rows[0].is_dofollow is True and rows[0].is_content is True
    assert rows[0].page_traffic is None
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    p = req.url.params
    assert p["target"] == "konkurrent.de"
    assert p["mode"] == "subdomains"
    assert p["aggregation"] == "1_per_domain"
    assert p["order_by"] == "domain_rating_source:desc"
    assert p["limit"] == "50"
    assert "traffic" not in p["select"].split(",")
    assert "is_dofollow" in p["select"].split(",") and "is_content" in p["select"].split(",")


@respx.mock
def test_fetch_with_traffic():
    resp = {"backlinks": [dict(RESPONSE["backlinks"][0], traffic=1200)]}
    route = respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=resp))
    rows = fetch_broken_backlinks("tok", "konkurrent.de", include_traffic=True)
    assert rows[0].page_traffic == 1200
    assert "traffic" in route.calls.last.request.url.params["select"].split(",")


@respx.mock
def test_api_error_is_readable():
    respx.get(AHREFS_URL).mock(return_value=httpx.Response(403, json={"error": "Insufficient units"}))
    with pytest.raises(AhrefsError, match="403"):
        fetch_broken_backlinks("tok", "konkurrent.de")


def test_missing_token():
    with pytest.raises(AhrefsError):
        fetch_broken_backlinks("", "konkurrent.de")


@respx.mock
def test_non_json_body_is_readable_error():
    respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, text="<html>maintenance</html>"))
    with pytest.raises(AhrefsError, match="JSON"):
        fetch_broken_backlinks("tok", "konkurrent.de")


@respx.mock
def test_rows_without_url_to_are_skipped():
    bad = {k: v for k, v in RESPONSE["backlinks"][1].items() if k != "url_to"}
    resp = {"backlinks": [RESPONSE["backlinks"][0], bad]}
    respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=resp))
    rows = fetch_broken_backlinks("tok", "konkurrent.de")
    assert len(rows) == 1
    assert rows[0].url_to == "https://konkurrent.de/ratgeber/stahl"


@respx.mock
def test_missing_backlinks_key_is_error():
    respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json={"error": "Insufficient units"}))
    with pytest.raises(AhrefsError, match="backlinks"):
        fetch_broken_backlinks("tok", "konkurrent.de")


@respx.mock
def test_blank_target_makes_no_request():
    route = respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=RESPONSE))
    with pytest.raises(AhrefsError):
        fetch_broken_backlinks("tok", "  ")
    assert not route.called


DEAD = {"or": [{"field": "http_code_target", "is": ["eq", 404]}, {"field": "http_code_target", "is": ["eq", 410]}]}
ALL_OFF = dict(dofollow_only=False, content_only=False, exclude_spam=False, dead_only=False)


def fetched_where(**kwargs):
    route = respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=RESPONSE))
    fetch_broken_backlinks("tok", "konkurrent.de", **kwargs)
    params = route.calls.last.request.url.params
    return json.loads(params["where"]) if "where" in params else None


@respx.mock
def test_default_where_is_dofollow_content_no_spam_dead_only():
    assert fetched_where() == {"and": [
        {"field": "is_dofollow", "is": ["eq", True]},
        {"field": "is_content", "is": ["eq", True]},
        {"field": "is_spam", "is": ["eq", False]},
        DEAD,
    ]}


@respx.mock
def test_all_filters_off_sends_no_where_param():
    assert fetched_where(**ALL_OFF) is None


@respx.mock
def test_single_filter_is_wrapped_in_and():
    assert fetched_where(**{**ALL_OFF, "dead_only": True}) == {"and": [DEAD]}


@respx.mock
def test_min_dr_appears_in_where():
    assert fetched_where(**ALL_OFF, min_dr=30) == {"and": [{"field": "domain_rating_source", "is": ["gte", 30]}]}


@respx.mock
def test_min_dr_zero_adds_nothing():
    assert fetched_where(**ALL_OFF, min_dr=0) is None


def test_language_filter_is_not_supported():
    with pytest.raises(TypeError):
        fetch_broken_backlinks("tok", "konkurrent.de", language="de")


@respx.mock
def test_flags_map_from_response_and_stay_none_when_absent():
    resp = {"backlinks": [
        dict(RESPONSE["backlinks"][0], is_dofollow=True, is_content=False),
        dict(RESPONSE["backlinks"][1], is_dofollow=False, is_content=True),
        {k: v for k, v in RESPONSE["backlinks"][1].items() if k not in ("is_dofollow", "is_content")},
    ]}
    respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=resp))
    rows = fetch_broken_backlinks("tok", "konkurrent.de", **ALL_OFF)
    assert (rows[0].is_dofollow, rows[0].is_content) == (True, False)
    assert (rows[1].is_dofollow, rows[1].is_content) == (False, True)
    assert (rows[2].is_dofollow, rows[2].is_content) == (None, None)


def test_describe_filters_defaults():
    assert describe_filters() == "Dofollow · Content-Links · ohne Spam · nur 404/410"


def test_describe_filters_all_off():
    assert describe_filters(**ALL_OFF) == "keine Filter"


def test_describe_filters_with_dr():
    assert describe_filters(min_dr=30) == "Dofollow · Content-Links · ohne Spam · nur 404/410 · DR ≥ 30"
    assert describe_filters(**ALL_OFF, min_dr=45.5) == "DR ≥ 45.5"
