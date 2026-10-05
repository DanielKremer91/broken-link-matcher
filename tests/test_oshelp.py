import oshelp


def test_keep_awake_uses_caffeinate_on_mac(monkeypatch):
    calls = []
    monkeypatch.setattr(oshelp.sys, "platform", "darwin")
    monkeypatch.setattr(oshelp, "_run_and_wait", lambda cmd: calls.append(cmd) or 0)
    assert oshelp.keep_awake(2.0) == 0
    assert calls == [["caffeinate", "-i", "-t", "7200"]]


def test_keep_awake_uses_execution_state_on_windows(monkeypatch):
    states, slept = [], []
    monkeypatch.setattr(oshelp.sys, "platform", "win32")
    monkeypatch.setattr(oshelp, "_set_windows_execution_state", lambda flags: states.append(flags))
    monkeypatch.setattr(oshelp.time, "sleep", lambda s: slept.append(s))
    assert oshelp.keep_awake(1.5) == 0
    assert states == [oshelp.ES_CONTINUOUS | oshelp.ES_SYSTEM_REQUIRED, oshelp.ES_CONTINUOUS]
    assert slept == [5400.0]


def test_keep_awake_elsewhere_only_says_so(monkeypatch, capsys):
    monkeypatch.setattr(oshelp.sys, "platform", "linux")
    assert oshelp.keep_awake(1) == 0
    assert "kein Schlafschutz" in capsys.readouterr().out


def test_open_file_picks_the_editor_per_system(monkeypatch, tmp_path):
    f = tmp_path / ".env"
    f.write_text("x")
    started = []
    monkeypatch.setattr(oshelp, "_start", lambda cmd: started.append(cmd))
    monkeypatch.setattr(oshelp.sys, "platform", "darwin")
    assert oshelp.open_file(f) == 0
    monkeypatch.setattr(oshelp.sys, "platform", "win32")
    assert oshelp.open_file(f) == 0
    assert started == [["open", "-e", str(f)], ["notepad", str(f)]]


def test_open_missing_file_fails(tmp_path, capsys):
    assert oshelp.main(["open", str(tmp_path / "fehlt.txt")]) == 1


def test_python_path_matches_the_running_system():
    assert oshelp.venv_python_hint("win32") == ".venv\\Scripts\\python.exe"
    assert oshelp.venv_python_hint("darwin") == ".venv/bin/python"
