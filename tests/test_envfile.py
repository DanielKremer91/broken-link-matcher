from blm.envfile import load_env_file


def test_missing_file_is_ignored(tmp_path, monkeypatch):
    assert load_env_file(tmp_path / ".env") == []


def test_sets_unset_variables_and_keeps_existing(tmp_path, monkeypatch):
    monkeypatch.delenv("BLM_TEST_A", raising=False)
    monkeypatch.setenv("BLM_TEST_B", "aus-shell")
    env = tmp_path / ".env"
    env.write_text('# Kommentar\nBLM_TEST_A="wert a"\nexport BLM_TEST_B=aus-datei\n\nkaputte zeile\n', encoding="utf-8")
    names = load_env_file(env)
    import os
    assert os.environ["BLM_TEST_A"] == "wert a"
    assert os.environ["BLM_TEST_B"] == "aus-shell"
    assert names == ["BLM_TEST_A"]
    monkeypatch.delenv("BLM_TEST_A")


def test_single_quotes_and_empty_values(tmp_path, monkeypatch):
    monkeypatch.delenv("BLM_TEST_C", raising=False)
    monkeypatch.delenv("BLM_TEST_D", raising=False)
    env = tmp_path / ".env"
    env.write_text("BLM_TEST_C='x y'\nBLM_TEST_D=\n", encoding="utf-8")
    load_env_file(env)
    import os
    assert os.environ["BLM_TEST_C"] == "x y"
    assert "BLM_TEST_D" not in os.environ
