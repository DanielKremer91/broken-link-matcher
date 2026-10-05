import json

import httpx
import pytest
import respx

import send_report
from blm.mailer import RESEND_URL


def no_sleep(_):
    pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_x")
    monkeypatch.setenv("RESEND_FROM", "Monitor <m@obs.com>")
    monkeypatch.setattr(send_report, "default_sleeper", no_sleep)
    repo = tmp_path / "repo"
    run_dir = repo / "laeufe" / "2026-11" / "zooroyal.de"
    run_dir.mkdir(parents=True)
    (run_dir / "bericht.md").write_text("Broken Link Chancen Fressnapf\nStand: November 2026\n", encoding="utf-8")
    (run_dir / "bericht.html").write_text("<p>Bericht</p>", encoding="utf-8")
    (run_dir / "ergebnis.xlsx").write_bytes(b"xlsx")
    (run_dir / "ergebnis-entwuerfe.md").write_text("Entwurf", encoding="utf-8")
    cfg = {"customer": "Fressnapf", "competitors": ["zooroyal.de", "zooplus.de"], "output_dir": "laeufe",
           "mail": {"method": "resend", "to": ["kunde@firma.de", "ich@obs.com"]}}
    path = repo / "monitor.config.json"

    def write(**changes):
        data = json.loads(json.dumps(cfg))
        data.update(changes)
        path.write_text(json.dumps(data), encoding="utf-8")
        return ["--config", str(path), "--run", "2026-11", "--env-file", str(tmp_path / "keine.env")]

    return write, repo, run_dir


@respx.mock
def test_report_goes_to_configured_recipients_with_files_from_the_run_folder(setup, capsys):
    write, repo, run_dir = setup
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "msg_1"}))
    assert send_report.main(write() + ["--competitor", "zooroyal.de"]) == 0
    body = json.loads(route.calls.last.request.content)
    assert body["to"] == ["kunde@firma.de", "ich@obs.com"]
    assert body["subject"] == "Broken Link Chancen Fressnapf" and body["html"] == "<p>Bericht</p>"
    assert [a["filename"] for a in body["attachments"]] == ["ergebnis.xlsx", "ergebnis-entwuerfe.md"]
    marker = json.loads((run_dir / "versendet.json").read_text(encoding="utf-8"))
    assert marker["id"] == "msg_1" and marker["to"] == ["kunde@firma.de", "ich@obs.com"]
    assert "re_x" not in capsys.readouterr().out


@respx.mock
def test_second_call_does_not_send_again_unless_resend(setup, capsys):
    write, _, _ = setup
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "m"}))
    args = write() + ["--competitor", "zooroyal.de"]
    assert send_report.main(args) == 0 and send_report.main(args) == 0
    assert route.call_count == 1 and "Bereits versendet" in capsys.readouterr().out
    assert send_report.main(args + ["--resend"]) == 0 and route.call_count == 2


def test_there_is_no_way_to_name_recipients_or_attachments():
    for flag in ("--to", "--attach", "--subject", "--html", "--text", "--marker"):
        with pytest.raises(SystemExit):
            send_report.main(["--competitor", "zooroyal.de", flag, "x"])


@pytest.mark.parametrize("competitor", ["fremd.de", "../..", "zooroyal.de/../../x", ""])
def test_unknown_competitor_is_refused(setup, capsys, competitor):
    write, _, _ = setup
    assert send_report.main(write() + ["--competitor", competitor]) == 1
    assert "competitors" in capsys.readouterr().err


@pytest.mark.parametrize("run", ["2026-13", "../2026-11", "2026-11/..", "abc"])
def test_bad_run_id_is_refused(setup, capsys, run):
    write, _, _ = setup
    args = write()
    args[args.index("--run") + 1] = run
    assert send_report.main(args + ["--competitor", "zooroyal.de"]) == 1


@pytest.mark.parametrize("output_dir", ["../raus", "/tmp/x", "laeufe/../.."])
def test_output_dir_must_stay_inside_the_repo(setup, capsys, output_dir):
    write, _, _ = setup
    assert send_report.main(write(output_dir=output_dir) + ["--competitor", "zooroyal.de"]) == 1
    assert "output_dir" in capsys.readouterr().err


def test_missing_report_files_fail_before_sending(setup, capsys):
    write, _, run_dir = setup
    (run_dir / "ergebnis.xlsx").unlink()
    assert send_report.main(write() + ["--competitor", "zooroyal.de"]) == 1
    assert "ergebnis.xlsx" in capsys.readouterr().err


def test_other_mail_methods_do_not_send(setup, capsys):
    write, _, _ = setup
    assert send_report.main(write(mail={"method": "file", "to": []}) + ["--competitor", "zooroyal.de"]) == 1
    assert "resend" in capsys.readouterr().err


@respx.mock
def test_error_mail_sends_fehler_md_without_marker(setup, capsys):
    write, repo, run_dir = setup
    (repo / "laeufe" / "2026-11" / "fehler.md").write_text("Schritt 2: Ahrefs lieferte nichts", encoding="utf-8")
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "e1"}))
    assert send_report.main(write() + ["--error"]) == 0
    body = json.loads(route.calls.last.request.content)
    assert body["subject"] == "Broken Link Monitor: Fehler im Lauf 2026-11"
    assert "Ahrefs lieferte nichts" in body["text"] and "attachments" not in body
    assert not (repo / "laeufe" / "2026-11" / "versendet.json").exists()


@respx.mock
def test_api_error_exits_1_and_writes_no_marker(setup, capsys):
    write, _, run_dir = setup
    respx.post(RESEND_URL).mock(return_value=httpx.Response(403, json={"message": "domain not verified"}))
    assert send_report.main(write() + ["--competitor", "zooroyal.de"]) == 1
    assert "domain not verified" in capsys.readouterr().err and not (run_dir / "versendet.json").exists()


def test_missing_key_exits_1(setup, monkeypatch, capsys):
    write, _, _ = setup
    monkeypatch.delenv("RESEND_API_KEY")
    assert send_report.main(write() + ["--competitor", "zooroyal.de"]) == 1
    assert "RESEND_API_KEY" in capsys.readouterr().err
