import json

import pytest

import check_setup


@pytest.fixture
def setup(tmp_path, monkeypatch):
    for var in ("OPENAI_API_KEY", "GEMINI_API_KEY", "RESEND_API_KEY", "RESEND_FROM"):
        monkeypatch.setenv(var, "")  # records the original state, so values loaded from .env are undone
        monkeypatch.delenv(var)
    repo = tmp_path / "repo"
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "python").write_text("")
    (repo / "cli.py").write_text("")
    frog_cfg = tmp_path / "frog.seospiderconfig"
    frog_cfg.write_text("x")
    cfg = {
        "repo_path": str(repo), "customer": "Fressnapf", "own_domain": "fressnapf.de", "start_url": "https://www.fressnapf.de/magazin/",
        "frog": {"crawl": True, "config_file": str(frog_cfg), "embeddings_file": ""},
        "competitors": ["zooroyal.de"], "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
        "ahrefs": {"limit": 100, "min_dr": 0}, "verify": True,
        "drafts": {"enabled": True, "sender": "Daniel"}, "contact": "",
        "mail": {"method": "resend", "to": ["d@obs.com"]}, "output_dir": "laeufe",
    }
    path = tmp_path / "monitor.config.json"

    def write(**changes):
        data = json.loads(json.dumps(cfg))
        for k, v in changes.items():
            data[k] = v
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    (repo / ".env").write_text("OPENAI_API_KEY=sk-geheim\nRESEND_API_KEY=re_geheim\nRESEND_FROM=Monitor <r@obs.com>\n")
    return write, repo


def run(path, capsys):
    rc = check_setup.main(["--config", str(path)])
    out = capsys.readouterr()
    return rc, out.out + out.err


def test_complete_setup_passes_without_printing_secrets(setup, capsys):
    write, _ = setup
    rc, out = run(write(), capsys)
    assert rc == 0, out
    assert "sk-geheim" not in out and "re_geheim" not in out
    assert "OPENAI_API_KEY" in out


def test_missing_keys_fail(setup, capsys):
    write, repo = setup
    (repo / ".env").unlink()
    rc, out = run(write(), capsys)
    assert rc == 1 and "OPENAI_API_KEY" in out and "RESEND_API_KEY" in out


def test_file_method_needs_no_resend_key(setup, capsys):
    write, repo = setup
    (repo / ".env").write_text("OPENAI_API_KEY=sk\n")
    rc, out = run(write(mail={"method": "file", "to": []}), capsys)
    assert rc == 0, out


def test_missing_frog_config_fails(setup, capsys):
    write, _ = setup
    rc, out = run(write(frog={"crawl": True, "config_file": "/gibt/es/nicht.seospiderconfig"}), capsys)
    assert rc == 1 and "Frog-Konfiguration" in out


def test_existing_export_instead_of_crawl(setup, tmp_path, capsys):
    write, _ = setup
    export = tmp_path / "emb.csv"
    export.write_text("url,embedding_0\n")
    rc, out = run(write(frog={"crawl": False, "embeddings_file": str(export)}), capsys)
    assert rc == 0, out


def test_competitor_with_protocol_fails(setup, capsys):
    write, _ = setup
    rc, out = run(write(competitors=["https://zooroyal.de/"]), capsys)
    assert rc == 1 and "ohne Protokoll" in out


def test_invalid_json_fails(tmp_path, capsys):
    path = tmp_path / "c.json"
    path.write_text("{kaputt")
    rc, out = run(path, capsys)
    assert rc == 1 and "JSON" in out


def test_unknown_provider_and_method_fail(setup, capsys):
    write, _ = setup
    rc, out = run(write(embedding={"provider": "foo", "model": "x"}, mail={"method": "brieftaube", "to": ["a@b.de"]}), capsys)
    assert rc == 1 and "provider" in out and "mail.method" in out


def test_missing_repo_fails(setup, capsys):
    write, _ = setup
    rc, out = run(write(repo_path="/gibt/es/nicht"), capsys)
    assert rc == 1 and "repo_path" in out


@pytest.mark.parametrize("comp", ["Zooroyal.de", "zooroyal.de/", "zooroyal"])
def test_competitor_must_be_plain_lowercase_domain(setup, capsys, comp):
    write, _ = setup
    rc, out = run(write(competitors=[comp]), capsys)
    assert rc == 1


def test_empty_or_relative_repo_path_fails(setup, capsys):
    write, _ = setup
    assert run(write(repo_path=""), capsys)[0] == 1
    assert run(write(repo_path="repo"), capsys)[0] == 1


def test_placeholder_sender_fails(setup, capsys):
    write, repo = setup
    (repo / ".env").write_text("OPENAI_API_KEY=sk\nRESEND_API_KEY=re\nRESEND_FROM=Monitor <monitor@deine-domain.de>\n")
    rc, out = run(write(), capsys)
    assert rc == 1 and "RESEND_FROM" in out


def test_missing_config_file_says_not_found(tmp_path, capsys):
    rc, out = run(tmp_path / "fehlt.json", capsys)
    assert rc == 1 and "nicht gefunden" in out


def test_bad_ahrefs_limit_fails(setup, capsys):
    write, _ = setup
    assert run(write(ahrefs={"limit": 0, "min_dr": 0}), capsys)[0] == 1
    rc, out = run(write(ahrefs={"limit": 100, "sprache": "de"}), capsys)
    assert rc == 1 and "Unbekannte Ahrefs-Einstellungen" in out


def test_embeddings_source_must_be_known(setup, capsys):
    write, _ = setup
    rc, out = run(write(frog={"crawl": False, "embeddings_file": "/x", "embeddings_source": "magie"}), capsys)
    assert rc == 1 and "embeddings_source" in out


def test_every_failed_item_explains_the_fix(setup, capsys):
    write, repo = setup
    (repo / ".env").unlink()
    rc, out = run(write(customer="", competitors=["https://k.de"]), capsys)
    lines = out.splitlines()
    failed = [i for i, line in enumerate(lines) if line.startswith("✗")]
    assert failed and all(lines[i + 1].startswith("  Lösung: ") for i in failed)
    assert "cp -n .env.example .env" in out and "nie in den Chat" in out


def test_inventory_works_without_config_and_hides_values(tmp_path, monkeypatch, capsys):
    for var in check_setup.KEY_NAMES:
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var)
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".env").write_text("OPENAI_API_KEY=sk-geheim\nRESEND_FROM=\n", encoding="utf-8")
    monkeypatch.setattr(check_setup, "__file__", str(repo / "check_setup.py"))
    frog_dir = tmp_path / "mcp"
    frog_dir.mkdir()
    monkeypatch.setattr(check_setup, "DEFAULT_FROG_DIR", frog_dir)
    rc = check_setup.main(["--inventory", "--config", str(repo / "monitor.config.json")])
    out = capsys.readouterr().out
    assert rc == 0 and "sk-geheim" not in out
    assert "✓ vorhanden: Schlüsseldatei .env" in out
    assert "✓ vorhanden: OPENAI_API_KEY eingetragen (bei OpenAI-Embeddings)" in out
    assert "○ fehlt: RESEND_FROM eingetragen (nur bei Versand über Resend)" in out
    assert "○ fehlt: Konfiguration monitor.config.json" in out
    assert "○ fehlt: Virtuelle Umgebung .venv" in out
    assert "○ fehlt: Frog-Konfigurationen im MCP-Ordner" in out
    (frog_dir / "broken-link-monitor-fressnapf.seospiderconfig").write_text("x")
    check_setup.main(["--inventory", "--config", str(repo / "monitor.config.json")])
    assert "broken-link-monitor-fressnapf.seospiderconfig (passt eine zu dieser Website?)" in capsys.readouterr().out


def test_inventory_uses_frog_path_from_config(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    frog = tmp_path / "x.seospiderconfig"
    frog.write_text("x")
    cfg = repo / "monitor.config.json"
    cfg.write_text(json.dumps({"frog": {"config_file": str(frog)}}), encoding="utf-8")
    monkeypatch.setattr(check_setup, "__file__", str(repo / "check_setup.py"))
    check_setup.main(["--inventory", "--config", str(cfg)])
    out = capsys.readouterr().out
    assert f"✓ vorhanden: Frog-Konfiguration {frog}" in out and "✓ vorhanden: Konfiguration" in out


def test_windows_style_venv_is_accepted(setup, capsys):
    write, repo = setup
    (repo / ".venv" / "bin" / "python").unlink()
    (repo / ".venv" / "bin").rmdir()
    (repo / ".venv" / "Scripts").mkdir()
    (repo / ".venv" / "Scripts" / "python.exe").write_text("")
    rc, out = run(write(), capsys)
    assert rc == 0, out


def test_start_url_must_belong_to_own_domain(setup, capsys):
    write, _ = setup
    rc, out = run(write(start_url="https://www.bora.com/de-de/ratgeber/"), capsys)
    assert rc == 1 and "start_url gehört zu own_domain" in out
    assert run(write(start_url="https://magazin.fressnapf.de/"), capsys)[0] == 0
