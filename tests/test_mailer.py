import base64
import json

import httpx
import pytest
import respx

import send_report
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


# ------------------------------------------------------------------ send_report.py

def bodies(tmp_path):
    html = tmp_path / "bericht.html"
    text = tmp_path / "bericht.md"
    html.write_text("<p>Bericht</p>", encoding="utf-8")
    text.write_text("Bericht", encoding="utf-8")
    return ["--html", str(html), "--text", str(text)]


def test_script_requires_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.setenv("RESEND_FROM", "a@b.de")
    rc = send_report.main(["--to", "d@obs.com", "--subject", "S", "--env-file", str(tmp_path / "keine.env")] + bodies(tmp_path))
    assert rc == 1 and "RESEND_API_KEY" in capsys.readouterr().err


def test_script_requires_sender(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.delenv("RESEND_FROM", raising=False)
    rc = send_report.main(["--to", "d@obs.com", "--subject", "S", "--env-file", str(tmp_path / "keine.env")] + bodies(tmp_path))
    assert rc == 1 and "RESEND_FROM" in capsys.readouterr().err


@respx.mock
def test_script_sends_and_never_prints_key(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)
    env = tmp_path / ".env"
    env.write_text("RESEND_API_KEY=re_supergeheim\nRESEND_FROM=Monitor <r@obs.com>\n", encoding="utf-8")
    att = tmp_path / "e.xlsx"
    att.write_bytes(b"x")
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "msg_9"}))
    rc = send_report.main(["--to", "d@obs.com", "--subject", "S", "--attach", str(att), "--env-file", str(env)]
                          + bodies(tmp_path))
    out = capsys.readouterr()
    assert rc == 0 and "msg_9" in out.out
    assert "re_supergeheim" not in out.out + out.err
    assert json.loads(route.calls.last.request.content)["html"] == "<p>Bericht</p>"
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("RESEND_FROM", raising=False)


@respx.mock
def test_script_api_error_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("RESEND_FROM", "a@b.de")
    monkeypatch.setattr(send_report, "default_sleeper", no_sleep)
    respx.post(RESEND_URL).mock(return_value=httpx.Response(422, json={"message": "invalid to"}))
    rc = send_report.main(["--to", "x", "--subject", "S", "--env-file", str(tmp_path / "keine.env")] + bodies(tmp_path))
    assert rc == 1 and "invalid to" in capsys.readouterr().err


def test_script_missing_body_file_exits_1(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("RESEND_FROM", "a@b.de")
    rc = send_report.main(["--to", "d@obs.com", "--subject", "S", "--html", str(tmp_path / "fehlt.html"),
                           "--env-file", str(tmp_path / "keine.env")])
    assert rc == 1



@respx.mock
def test_separate_calls_use_different_idempotency_keys():
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "x"}))
    with httpx.Client() as client:
        for _ in range(2):
            send_resend("k", "a@b.de", ["c@d.de"], "S", "h", "t", [], client=client, sleeper=no_sleep)
    assert len({c.request.headers["Idempotency-Key"] for c in route.calls}) == 2


# ------------------------------------------------------------------ sent marker

@respx.mock
def test_marker_written_after_send_and_blocks_second_send(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("RESEND_FROM", "a@b.de")
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "msg_1"}))
    marker = tmp_path / "lauf" / "versendet.json"
    args = ["--to", "d@obs.com", "--subject", "S", "--env-file", str(tmp_path / "keine.env"),
            "--marker", str(marker)] + bodies(tmp_path)
    assert send_report.main(args) == 0
    data = json.loads(marker.read_text(encoding="utf-8"))
    assert data["id"] == "msg_1" and data["to"] == ["d@obs.com"] and data["subject"] == "S" and "sent_at" in data
    capsys.readouterr()
    assert send_report.main(args) == 0
    out = capsys.readouterr().out
    assert route.call_count == 1 and "Bereits versendet" in out and "msg_1" in out


@respx.mock
def test_resend_flag_sends_again_and_updates_marker(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("RESEND_FROM", "a@b.de")
    route = respx.post(RESEND_URL).mock(side_effect=[httpx.Response(200, json={"id": "m1"}),
                                                     httpx.Response(200, json={"id": "m2"})])
    marker = tmp_path / "versendet.json"
    args = ["--to", "d@obs.com", "--subject", "S", "--env-file", str(tmp_path / "keine.env"),
            "--marker", str(marker)] + bodies(tmp_path)
    assert send_report.main(args) == 0 and send_report.main(args + ["--resend"]) == 0
    assert route.call_count == 2 and json.loads(marker.read_text(encoding="utf-8"))["id"] == "m2"


@respx.mock
def test_failed_send_writes_no_marker(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("RESEND_FROM", "a@b.de")
    monkeypatch.setattr(send_report, "default_sleeper", no_sleep)
    respx.post(RESEND_URL).mock(return_value=httpx.Response(403, json={"message": "nope"}))
    marker = tmp_path / "versendet.json"
    rc = send_report.main(["--to", "d@obs.com", "--subject", "S", "--env-file", str(tmp_path / "keine.env"),
                           "--marker", str(marker)] + bodies(tmp_path))
    assert rc == 1 and not marker.exists()
