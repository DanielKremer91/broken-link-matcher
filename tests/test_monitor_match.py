import json
from pathlib import Path

import pandas as pd
import pytest
import respx

import cli
import monitor_match
from tests.test_pipeline import KeywordProvider, mock_wayback

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: KeywordProvider())
    monkeypatch.setattr(cli, "default_sleeper", lambda s: None)
    monkeypatch.setattr(cli, "DEFAULT_ENV_FILE", tmp_path / "keine.env")
    repo = tmp_path / "repo"
    run_dir = repo / "laeufe" / "2026-11" / "konkurrent.de"
    run_dir.mkdir(parents=True)
    (run_dir / "broken-backlinks.csv").write_text((FIX / "pipeline_backlinks.csv").read_text(encoding="utf-8"), encoding="utf-8")
    cfg = {"customer": "Fressnapf", "own_domain": "me.de", "competitors": ["konkurrent.de"], "output_dir": "laeufe",
           "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
           "ahrefs": {"limit": 50, "min_dr": 10}, "verify": False,
           "drafts": {"enabled": False, "sender": "Daniel"}, "contact": "seo@me.de",
           "mail": {"method": "file", "to": []}}
    path = repo / "monitor.config.json"

    def write(**changes):
        data = json.loads(json.dumps(cfg))
        data.update(changes)
        path.write_text(json.dumps(data), encoding="utf-8")
        return ["--config", str(path), "--run", "2026-11", "--competitor", "konkurrent.de",
                "--frog", str(FIX / "pipeline_frog.csv"), "--cache-dir", str(tmp_path / "cache")]

    return write, repo, run_dir


def test_cli_arguments_come_from_the_config(setup):
    write, repo, run_dir = setup
    args = write()
    cfg = json.loads((repo / "monitor.config.json").read_text(encoding="utf-8"))
    argv = monitor_match.build_cli_args(cfg, repo, "2026-11", "konkurrent.de", FIX / "pipeline_frog.csv", ["Hinweis A"])
    joined = " ".join(argv)
    assert f"--backlinks {run_dir / 'broken-backlinks.csv'}" in joined
    assert f"--out {run_dir / 'ergebnis.xlsx'}" in joined and f"--report {run_dir / 'bericht.md'}" in joined
    assert f"--seen-file {repo / 'laeufe' / 'verlauf-konkurrent.de.json'}" in joined
    assert "--provider openai --model text-embedding-3-small" in joined
    assert "--limit 50 --min-dr 10" in joined and "--run-id 2026-11" in joined
    assert "--competitor konkurrent.de --customer Fressnapf" in joined
    assert "--contact seo@me.de" in joined and "--note Hinweis A" in joined
    assert "--verify" not in argv and "--drafts" not in argv


def test_verify_and_drafts_follow_the_config(setup):
    write, repo, _ = setup
    write(verify=True, drafts={"enabled": True, "sender": "Daniel Kremer"})
    cfg = json.loads((repo / "monitor.config.json").read_text(encoding="utf-8"))
    argv = monitor_match.build_cli_args(cfg, repo, "2026-11", "konkurrent.de", Path("f.csv"), [])
    assert "--verify" in argv and "--drafts" in argv
    assert argv[argv.index("--sender") + 1] == "Daniel Kremer" and argv[argv.index("--domain") + 1] == "me.de"


@respx.mock
def test_run_writes_report_excel_and_history_into_the_run_folder(setup, capsys):
    write, repo, run_dir = setup
    mock_wayback()
    assert monitor_match.main(write()) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["report_subject"] == "Broken Link Chancen Fressnapf" and data["run_id"] == "2026-11"
    assert (run_dir / "bericht.html").is_file() and (repo / "laeufe" / "verlauf-konkurrent.de.json").is_file()
    assert "Linkgebende URL" in pd.read_excel(run_dir / "ergebnis.xlsx").columns


@pytest.mark.parametrize("flag", ["--out", "--backlinks", "--report", "--seen-file", "--env-file", "--sender"])
def test_no_free_paths_or_identities(setup, flag):
    write, _, _ = setup
    with pytest.raises(SystemExit):
        monitor_match.main(write() + [flag, "x"])


def test_unknown_competitor_and_missing_backlink_file_fail(setup, capsys):
    write, repo, run_dir = setup
    args = write()
    args[args.index("--competitor") + 1] = "../.."
    assert monitor_match.main(args) == 1
    (run_dir / "broken-backlinks.csv").unlink()
    assert monitor_match.main(write()) == 1
    assert "broken-backlinks.csv" in capsys.readouterr().err
