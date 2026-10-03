import json
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

import cli
from blm.pipeline import PipelineResult, PipelineSummary
from tests.test_pipeline import KeywordProvider, mock_wayback

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def no_repo_env_file(monkeypatch, tmp_path):
    # a real .env in the repo must never leak into tests
    monkeypatch.setattr(cli, "DEFAULT_ENV_FILE", tmp_path / "keine.env")


@pytest.fixture
def fake_provider(monkeypatch):
    prov = KeywordProvider()
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: prov)
    monkeypatch.setattr(cli, "default_sleeper", lambda s: None)
    return prov


def base_args(tmp_path, out="ergebnis.xlsx"):
    return ["--frog", str(FIX / "pipeline_frog.csv"), "--backlinks", str(FIX / "pipeline_backlinks.csv"),
            "--provider", "openai", "--model", "text-embedding-3-small", "--out", str(tmp_path / out),
            "--cache-dir", str(tmp_path / "cache")]


def test_missing_key_exits_1_with_hint(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(base_args(tmp_path)) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


@respx.mock
def test_run_writes_xlsx_and_prints_summary(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    assert cli.main(base_args(tmp_path)) == 0
    df = pd.read_excel(tmp_path / "ergebnis.xlsx")
    assert len(df) == 2 and df.loc[0, "Vorschlag 1"] == "https://me.de/kueche-aus-stahl"
    out = capsys.readouterr()
    assert "Treffer" in out.out and "2" in out.out


@respx.mock
def test_json_output_is_machine_readable(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    assert cli.main(base_args(tmp_path, out="e.csv") + ["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["matched"] == 2 and data["output"].endswith("e.csv")
    assert (tmp_path / "e.csv").read_bytes().startswith("﻿".encode())


@respx.mock
def test_drafts_written_as_markdown(monkeypatch, tmp_path, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Hallo Entwurf"}}]}))
    args = base_args(tmp_path) + ["--drafts", "--sender", "Daniel", "--domain", "me.de",
                                  "--drafts-out", str(tmp_path / "drafts.md")]
    assert cli.main(args) == 0
    md = (tmp_path / "drafts.md").read_text()
    assert md.count("Hallo Entwurf") == 2 and "https://blog.example/kueche" in md


def test_drafts_without_sender_exit_1(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert cli.main(base_args(tmp_path) + ["--drafts"]) == 1
    assert "sender" in capsys.readouterr().err.lower()


def test_unknown_file_exits_1(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    args = base_args(tmp_path)
    args[args.index("--frog") + 1] = str(tmp_path / "nope.csv")
    assert cli.main(args) == 1
    assert "Frog" in capsys.readouterr().err


def test_bad_out_extension_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(base_args(tmp_path, out="e.txt"))
    assert exc.value.code == 2


def test_ollama_needs_no_key(monkeypatch, tmp_path, fake_provider):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    with respx.mock:
        mock_wayback()
        args = base_args(tmp_path)
        args[args.index("--provider") + 1] = "ollama"
        assert cli.main(args) == 0


def test_help_exits_0_and_offers_no_key_option(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "api-key" not in capsys.readouterr().out.lower()


@respx.mock
def test_key_value_never_leaks_into_output_or_files(monkeypatch, tmp_path, capsys, fake_provider):
    secret = "sk-test-secret-value"
    monkeypatch.setenv("OPENAI_API_KEY", secret)
    mock_wayback()
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Hallo Entwurf"}}]}))
    args = base_args(tmp_path, out="e.csv") + ["--json", "--drafts", "--sender", "Daniel", "--domain", "me.de",
                                              "--drafts-out", str(tmp_path / "drafts.md")]
    assert cli.main(args) == 0
    captured = capsys.readouterr()
    assert secret not in captured.out and secret not in captured.err
    assert secret.encode() not in (tmp_path / "e.csv").read_bytes()
    assert secret not in (tmp_path / "drafts.md").read_text()


def test_out_pointing_at_directory_exits_1_before_provider(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = []
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: built.append(1))
    args = base_args(tmp_path)
    args[args.index("--out") + 1] = str(tmp_path)
    assert cli.main(args) == 1
    assert "Verzeichnis" in capsys.readouterr().err
    assert built == []


def test_drafts_out_pointing_at_directory_exits_1_before_provider(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = []
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: built.append(1))
    args = base_args(tmp_path) + ["--drafts", "--sender", "D", "--domain", "me.de", "--drafts-out", str(tmp_path)]
    assert cli.main(args) == 1
    assert "Verzeichnis" in capsys.readouterr().err
    assert built == []


def test_unusable_output_parent_exits_1_before_provider(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    built = []
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: built.append(1))
    blocker = tmp_path / "datei"
    blocker.write_text("x")
    args = base_args(tmp_path)
    args[args.index("--out") + 1] = str(blocker / "sub" / "e.xlsx")
    assert cli.main(args) == 1
    assert "Abbruch" in capsys.readouterr().err
    assert built == []


@respx.mock
def test_write_failure_after_run_exits_1_without_traceback(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()

    def boom(*a, **k):
        raise PermissionError("gesperrt")

    monkeypatch.setattr(cli, "write_output", boom)
    assert cli.main(base_args(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "Ergebnisdatei konnte nicht geschrieben werden" in err and "gesperrt" in err


@respx.mock
def test_drafts_default_to_file_next_to_out(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Hallo Entwurf"}}]}))
    args = base_args(tmp_path) + ["--drafts", "--sender", "D", "--domain", "me.de", "--json"]
    assert cli.main(args) == 0
    default = tmp_path / "ergebnis-entwuerfe.md"
    assert default.read_text().count("Hallo Entwurf") == 2
    assert json.loads(capsys.readouterr().out)["drafts_output"] == str(default)


def test_write_output_writes_drafts_before_results(tmp_path):
    result = PipelineResult(results=[], summary=PipelineSummary(), drafts={"https://a.de|https://b.de": "T"})
    blocked = tmp_path / "ordner"
    blocked.mkdir()
    drafts = tmp_path / "d.md"
    with pytest.raises(OSError):
        cli.write_output(result, blocked, drafts)  # results path is a directory
    assert drafts.exists()


@pytest.mark.parametrize("flag,value", [("--pause", "-1"), ("--limit", "0"), ("--limit", "-5"),
                                        ("--max-chars", "999"), ("--min-dr", "-1"), ("--min-dr", "101")])
def test_invalid_numeric_arguments_exit_2(tmp_path, flag, value):
    with pytest.raises(SystemExit) as exc:
        cli.main(base_args(tmp_path) + [flag, value])
    assert exc.value.code == 2


def test_write_output_splits_drafts_key_and_strips_occurrence_suffix(tmp_path):
    result = PipelineResult(
        results=[], summary=PipelineSummary(),
        drafts={"https://a.de/x|https://dead.de/y": "Erster", "https://a.de/x|https://dead.de/y#2": "Zweiter"},
    )
    drafts = tmp_path / "d.md"
    cli.write_output(result, tmp_path / "o.csv", drafts)
    md = drafts.read_text()
    assert "Tote URL: https://dead.de/y\n" in md and "#2" not in md
    assert "Erster" in md and "Zweiter" in md


def test_summary_lines_mention_excel_date_repairs_only_when_present():
    assert not any("Excel" in line for line in cli.summary_lines(PipelineSummary()))
    lines = cli.summary_lines(PipelineSummary(excel_dates_repaired=19))
    assert "Hinweis: 19 Excel-Datumswerte zurückgerechnet" in lines


# ------------------------------------------------------------------ monthly monitor

@respx.mock
def test_seen_file_marks_new_rows_and_records_reported(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    seen = tmp_path / "verlauf" / "seen.json"
    seen.parent.mkdir()
    seen.write_text(json.dumps({"keys": {"blog.example/kueche|konkurrent.de/ratgeber/stahl":
                                         {"status": "match", "since": "2026-09"}}}), encoding="utf-8")
    assert cli.main(base_args(tmp_path) + ["--seen-file", str(seen), "--run-id", "2026-10", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["new_rows"] == 1 and data["run_id"] == "2026-10"
    df = pd.read_excel(tmp_path / "ergebnis.xlsx")
    assert list(df["Neu"]) == ["Nein", "Ja"]
    keys = json.loads(seen.read_text(encoding="utf-8"))["keys"]
    assert keys["forum.example/t/1|konkurrent.de/holz"]["since"] == "2026-10"
    assert keys["blog.example/kueche|konkurrent.de/ratgeber/stahl"]["since"] == "2026-09"


@respx.mock
def test_rerun_same_month_repeats_report_next_month_has_nothing_new(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    seen = tmp_path / "seen.json"
    args = base_args(tmp_path) + ["--seen-file", str(seen), "--report", str(tmp_path / "bericht.md"), "--json"]
    assert cli.main(args + ["--run-id", "2026-10"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["new_opportunities"] >= 1
    assert cli.main(args + ["--run-id", "2026-10"]) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["new_opportunities"] == first["new_opportunities"]
    assert again["report_subject"] == first["report_subject"]
    assert cli.main(args + ["--run-id", "2026-11"]) == 0
    later = json.loads(capsys.readouterr().out)
    assert later["new_opportunities"] == 0 and later["opportunities"] == first["opportunities"]
    assert "davon 0 neu" in (tmp_path / "bericht.md").read_text(encoding="utf-8")
    df = pd.read_excel(tmp_path / "ergebnis.xlsx")
    assert set(df.loc[df["Neu"] == "Nein", "Erstmals erfasst"].dropna()) == {"2026-10"}


@respx.mock
def test_fixed_rows_are_not_recorded(monkeypatch, tmp_path, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    import blm.pipeline as pipeline_mod

    def all_fixed(results, client, **kw):
        for r in results:
            r.verification = "fixed"
    monkeypatch.setattr(pipeline_mod, "verify_results", all_fixed)
    seen = tmp_path / "seen.json"
    assert cli.main(base_args(tmp_path) + ["--seen-file", str(seen), "--verify"]) == 0
    assert json.loads(seen.read_text(encoding="utf-8"))["keys"] == {}


@respx.mock
def test_report_files_written_with_competitor_from_urls(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    report = tmp_path / "bericht.md"
    assert cli.main(base_args(tmp_path) + ["--report", str(report), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["report"] == str(report) and data["report_html"] == str(tmp_path / "bericht.html")
    assert data["report_subject"] == "Broken Link Chancen"
    assert "Wettbewerber: konkurrent.de" in report.read_text(encoding="utf-8")
    assert "blog.example" in report.read_text(encoding="utf-8")
    assert (tmp_path / "bericht.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    # without --seen-file there is no history: no "Neu" column, no "neu" wording, no new_rows
    assert "Neu" not in pd.read_excel(tmp_path / "ergebnis.xlsx").columns
    assert "Neu seit dem letzten Bericht" not in report.read_text(encoding="utf-8") and "new_rows" not in data


@respx.mock
def test_competitor_label_can_be_set(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    assert cli.main(base_args(tmp_path) + ["--report", str(tmp_path / "b.md"), "--competitor", "zooroyal.de",
                                           "--customer", "Fressnapf", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["report_subject"] == "Broken Link Chancen Fressnapf"
    assert "Wettbewerber: zooroyal.de" in (tmp_path / "b.md").read_text(encoding="utf-8")


def test_corrupt_seen_file_exits_1_before_provider(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    seen = tmp_path / "seen.json"
    seen.write_text("{kaputt", encoding="utf-8")
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: pytest.fail("provider must not be built"))
    assert cli.main(base_args(tmp_path) + ["--seen-file", str(seen)]) == 1
    assert "Verlaufsdatei" in capsys.readouterr().err


def test_report_needs_md_or_txt_suffix(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(base_args(tmp_path) + ["--report", str(tmp_path / "bericht.html")])
    assert exc.value.code == 2


@respx.mock
def test_key_from_env_file(monkeypatch, tmp_path, fake_provider):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    mock_wayback()
    env = tmp_path / ".env"
    env.write_text("OPENAI_API_KEY=sk-aus-datei\n", encoding="utf-8")
    assert cli.main(base_args(tmp_path) + ["--env-file", str(env)]) == 0
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@respx.mock
def test_unmatched_rows_are_not_remembered(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    seen = tmp_path / "seen.json"
    # --no-fallback leaves the row without snapshot unmatched
    assert cli.main(base_args(tmp_path) + ["--seen-file", str(seen), "--no-fallback"]) == 0
    keys = set(json.loads(seen.read_text(encoding="utf-8"))["keys"])
    assert set(keys) == {"blog.example/kueche|konkurrent.de/ratgeber/stahl"}


def test_unreadable_env_file_exits_1(monkeypatch, tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_bytes(b"OPENAI_API_KEY=\xff\xfe")
    assert cli.main(base_args(tmp_path) + ["--env-file", str(env)]) == 1
    assert "Schlüsseldatei" in capsys.readouterr().err


@respx.mock
def test_notes_appear_in_report_and_json(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    report = tmp_path / "bericht.md"
    note = "Crawl unvollständig: 450 von 1340 Seiten ohne Antwort"
    assert cli.main(base_args(tmp_path) + ["--report", str(report), "--note", note, "--note", " ", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert note in data["errors"] and " " not in data["errors"]
    assert f"Hinweis zum Lauf: {note}" in report.read_text(encoding="utf-8")
