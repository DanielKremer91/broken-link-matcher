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


def test_key_never_appears_in_help_or_errors(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    assert "api-key" not in capsys.readouterr().out.lower()


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
