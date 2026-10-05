import base64
import json

import httpx
import pytest
import respx

from blm.mailer import RESEND_URL, MailError, send_resend


def no_sleep(_):
    pass


@respx.mock
def test_send_posts_payload_with_attachments(tmp_path):
    att = tmp_path / "ergebnis.xlsx"
    att.write_bytes(b"\x00\x01excel")
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "msg_123"}))
    with httpx.Client() as client:
        msg_id = send_resend("re_test", "Monitor <r@obs.com>", ["d@obs.com"], "Betreff", "<p>Hi</p>", "Hi",
                             [att], client=client, sleeper=no_sleep)
    assert msg_id == "msg_123"
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer re_test"
    body = json.loads(req.content)
    assert body["from"] == "Monitor <r@obs.com>" and body["to"] == ["d@obs.com"]
    assert body["subject"] == "Betreff" and body["html"] == "<p>Hi</p>" and body["text"] == "Hi"
    assert body["attachments"] == [{"filename": "ergebnis.xlsx", "content": base64.b64encode(b"\x00\x01excel").decode()}]


@respx.mock
def test_error_message_from_api_is_reported_without_key():
    respx.post(RESEND_URL).mock(return_value=httpx.Response(403, json={"message": "domain not verified"}))
    with httpx.Client() as client, pytest.raises(MailError) as exc:
        send_resend("re_geheim", "a@b.de", ["c@d.de"], "S", "<p/>", "t", [], client=client, sleeper=no_sleep)
    assert "403" in str(exc.value) and "domain not verified" in str(exc.value)
    assert "re_geheim" not in str(exc.value)


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.post(RESEND_URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json={"id": "ok"})])
    with httpx.Client() as client:
        assert send_resend("k", "a@b.de", ["c@d.de"], "S", "h", "t", [], client=client, sleeper=no_sleep) == "ok"
    assert route.call_count == 2
    keys = {c.request.headers["Idempotency-Key"] for c in route.calls}
    assert len(keys) == 1 and next(iter(keys)).startswith("blm-")


@respx.mock
def test_network_error_becomes_mail_error():
    respx.post(RESEND_URL).mock(side_effect=httpx.ConnectError("weg"))
    with httpx.Client() as client, pytest.raises(MailError):
        send_resend("k", "a@b.de", ["c@d.de"], "S", "h", "t", [], client=client, sleeper=no_sleep)


def test_missing_attachment_raises_before_request(tmp_path):
    with pytest.raises(MailError, match="Anhang"):
        send_resend("k", "a@b.de", ["c@d.de"], "S", "h", "t", [tmp_path / "fehlt.xlsx"], sleeper=no_sleep)


def test_oversized_attachments_raise(tmp_path, monkeypatch):
    big = tmp_path / "gross.bin"
    big.write_bytes(b"x" * 20)
    monkeypatch.setattr("blm.mailer.MAX_ATTACHMENT_BYTES", 10)
    with pytest.raises(MailError, match="zu groß"):
        send_resend("k", "a@b.de", ["c@d.de"], "S", "h", "t", [big], sleeper=no_sleep)
