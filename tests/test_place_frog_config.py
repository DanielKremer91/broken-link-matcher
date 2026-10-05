import os
import time

import place_frog_config as pfc


def make(path, content="x", age_minutes=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if age_minutes:
        t = time.time() - age_minutes * 60
        os.utime(path, (t, t))
    return path


def run(tmp_path, capsys, *extra):
    target = tmp_path / "mcp" / "broken-link-monitor-bora.seospiderconfig"
    rc = pfc.main(["--target", str(target), "--search", str(tmp_path / "Desktop"), str(tmp_path / "home"), *extra])
    return rc, capsys.readouterr().out, target


def test_moves_file_with_expected_name_and_restricts_permissions(tmp_path, capsys):
    src = make(tmp_path / "Desktop" / "broken-link-monitor-bora.seospiderconfig", "geheim")
    rc, out, target = run(tmp_path, capsys)
    assert rc == 0 and target.read_text() == "geheim" and not src.exists()
    assert oct(target.stat().st_mode & 0o777) == "0o600"
    assert "verschoben" in out and "geheim" not in out


def test_finds_file_whose_name_carries_the_typed_path(tmp_path, capsys):
    make(tmp_path / "home" / "seo_spider_mcp_server:broken-link-monitor-bora.seospiderconfig")
    rc, out, target = run(tmp_path, capsys)
    assert rc == 0 and target.exists()


def test_falls_back_to_single_recent_config_with_other_name(tmp_path, capsys):
    make(tmp_path / "Desktop" / "bora neu.seospiderconfig", age_minutes=5)
    make(tmp_path / "Desktop" / "uralt.seospiderconfig", age_minutes=60 * 24 * 30)
    rc, out, target = run(tmp_path, capsys)
    assert rc == 0 and target.exists() and (tmp_path / "Desktop" / "uralt.seospiderconfig").exists()


def test_several_recent_candidates_are_listed_not_moved(tmp_path, capsys):
    make(tmp_path / "Desktop" / "a.seospiderconfig", age_minutes=3)
    make(tmp_path / "home" / "b.seospiderconfig", age_minutes=4)
    rc, out, target = run(tmp_path, capsys)
    assert rc == 2 and not target.exists()
    assert "a.seospiderconfig" in out and "b.seospiderconfig" in out


def test_nothing_found_explains_what_to_do(tmp_path, capsys):
    (tmp_path / "Desktop").mkdir()
    rc, out, target = run(tmp_path, capsys)
    assert rc == 1 and "broken-link-monitor-bora.seospiderconfig" in out and "Downloads" in out


def test_existing_target_is_kept_when_nothing_new_and_backed_up_when_replaced(tmp_path, capsys):
    target = make(tmp_path / "mcp" / "broken-link-monitor-bora.seospiderconfig", "alt")
    (tmp_path / "Desktop").mkdir()
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 0 and "liegt bereits" in out and target.read_text() == "alt"
    make(tmp_path / "Desktop" / "broken-link-monitor-bora.seospiderconfig", "neu")
    rc, out, _ = run(tmp_path, capsys)
    assert rc == 0 and target.read_text() == "neu"
    assert (target.parent / (target.name + ".vorher")).read_text() == "alt"


def test_explicit_source(tmp_path, capsys):
    src = make(tmp_path / "irgendwo" / "x.seospiderconfig", age_minutes=600)
    rc, out, target = run(tmp_path, capsys, "--source", str(src))
    assert rc == 0 and target.exists() and not src.exists()


def test_default_search_starts_with_downloads():
    assert pfc.DEFAULT_SEARCH[0] == "~/Downloads"


def test_unreadable_folder_is_reported(tmp_path, capsys):
    import os
    import pytest
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    locked = tmp_path / "Desktop"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        rc, out, _ = run(tmp_path, capsys)
    finally:
        locked.chmod(0o755)
    assert rc == 1 and "Kein Zugriff" in out and str(locked) in out


def test_denied_folder_is_not_mentioned_when_the_file_was_found(tmp_path, capsys):
    import os
    import pytest
    if os.geteuid() == 0:
        pytest.skip("root reads everything")
    make(tmp_path / "home" / "broken-link-monitor-bora.seospiderconfig")
    locked = tmp_path / "Desktop"
    locked.mkdir()
    locked.chmod(0o000)
    try:
        rc, out, target = run(tmp_path, capsys)
    finally:
        locked.chmod(0o755)
    assert rc == 0 and target.exists() and "Kein Zugriff" not in out
