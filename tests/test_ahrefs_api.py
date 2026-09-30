import json
from pathlib import Path

import httpx
import pytest
import respx

from blm.ingest.ahrefs_api import AHREFS_URL, AhrefsError, fetch_broken_backlinks

FIX = Path(__file__).parent / "fixtures"
RESPONSE = json.loads((FIX / "ahrefs_api_response.json").read_text())


@respx.mock
def test_fetch_maps_fields_and_sets_dofollow_content_true():
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
    where = json.loads(p["where"])
    assert {"field": "is_dofollow", "is": ["eq", True]} in where["and"]
    assert {"field": "is_content", "is": ["eq", True]} in where["and"]


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
