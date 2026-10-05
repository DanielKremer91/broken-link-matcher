import json
import os
import time

import frog_state


def lock(tmp_path, customer, run="2026-11"):
    return frog_state.main(["lock", "--dir", str(tmp_path), "--customer", customer, "--run", run])


def test_lock_is_free_then_busy_for_everyone_including_a_second_run_of_the_owner(tmp_path, capsys):
    assert lock(tmp_path, "fressnapf") == 0
    capsys.readouterr()
    assert lock(tmp_path, "bora") == 3
    assert "fressnapf" in capsys.readouterr().out
    assert lock(tmp_path, "fressnapf") == 3
    assert "denselben Kunden" in capsys.readouterr().out


def test_refresh_keeps_a_long_run_from_going_stale(tmp_path):
    lock(tmp_path, "fressnapf")
    path = tmp_path / frog_state.LOCK_NAME
    old = time.time() - (frog_state.STALE_HOURS - 1) * 3600
    os.utime(path, (old, old))
    assert frog_state.main(["refresh", "--dir", str(tmp_path), "--customer", "fressnapf"]) == 0
    assert time.time() - path.stat().st_mtime < 60
    assert frog_state.main(["refresh", "--dir", str(tmp_path), "--customer", "bora"]) == 1


def test_stale_limit_covers_wait_plus_two_crawls():
    assert frog_state.STALE_HOURS >= 13


def test_unlock_only_by_owner_then_free(tmp_path):
    lock(tmp_path, "fressnapf")
    assert frog_state.main(["unlock", "--dir", str(tmp_path), "--customer", "bora"]) == 0
    assert lock(tmp_path, "bora") == 3
    assert frog_state.main(["unlock", "--dir", str(tmp_path), "--customer", "fressnapf"]) == 0
    assert lock(tmp_path, "bora") == 0


def test_stale_lock_is_taken_over(tmp_path):
    lock(tmp_path, "fressnapf")
    path = tmp_path / frog_state.LOCK_NAME
    old = time.time() - (frog_state.STALE_HOURS + 1) * 3600
    os.utime(path, (old, old))
    assert lock(tmp_path, "bora") == 0
    assert json.loads(path.read_text(encoding="utf-8"))["customer"] == "bora"


def test_corrupt_lock_counts_as_free(tmp_path):
    (tmp_path / frog_state.LOCK_NAME).write_text("{kaputt", encoding="utf-8")
    assert lock(tmp_path, "bora") == 0


def config(tmp_path, **changes):
    frog_cfg = tmp_path / "x.seospiderconfig"
    if not frog_cfg.exists():
        frog_cfg.write_text("x")
    cfg = {"start_url": "https://a.de/magazin/", "embedding": {"provider": "openai", "model": "text-embedding-3-small"},
           "frog": {"config_file": str(frog_cfg), "embeddings_source": "custom_javascript", "custom_js_field": ""}}
    for key, value in changes.items():
        if key in cfg["frog"]:
            cfg["frog"][key] = value
        elif key == "model":
            cfg["embedding"]["model"] = value
        else:
            cfg[key] = value
    path = tmp_path / "monitor.config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path, frog_cfg


def test_meta_matches_until_a_relevant_setting_changes(tmp_path, capsys):
    cfg, frog_cfg = config(tmp_path)
    meta = tmp_path / "meta.json"
    assert frog_state.main(["save-meta", "--config", str(cfg), "--meta", str(meta)]) == 0
    assert frog_state.main(["check-meta", "--config", str(cfg), "--meta", str(meta)]) == 0
    for change in ({"start_url": "https://a.de/ratgeber/"}, {"model": "text-embedding-3-large"},
                   {"embeddings_source": "ai"}):
        cfg, _ = config(tmp_path, **change)
        capsys.readouterr()
        assert frog_state.main(["check-meta", "--config", str(cfg), "--meta", str(meta)]) == 1
        assert "geändert" in capsys.readouterr().out
    cfg, _ = config(tmp_path)
    assert frog_state.main(["check-meta", "--config", str(cfg), "--meta", str(meta)]) == 0


def test_meta_differs_when_frog_config_file_was_saved_again(tmp_path):
    cfg, frog_cfg = config(tmp_path)
    meta = tmp_path / "meta.json"
    frog_state.main(["save-meta", "--config", str(cfg), "--meta", str(meta)])
    later = time.time() + 120
    os.utime(frog_cfg, (later, later))
    assert frog_state.main(["check-meta", "--config", str(cfg), "--meta", str(meta)]) == 1


def test_missing_meta_means_no_reuse(tmp_path):
    cfg, _ = config(tmp_path)
    assert frog_state.main(["check-meta", "--config", str(cfg), "--meta", str(tmp_path / "fehlt.json")]) == 1


def test_discard_removes_only_this_months_crawl_files(tmp_path):
    names = ["a.de-2026-11.ndjson", "a.de-2026-11-meta.json", "a.de-2026-11-stichprobe.ndjson",
             "a.de-2026-11-intern.ndjson", "a.de-2026-10.ndjson", "b.de-2026-11.ndjson", "andere.txt"]
    for n in names:
        (tmp_path / n).write_text("x")
    assert frog_state.main(["discard", "--dir", str(tmp_path), "--domain", "a.de", "--run", "2026-11"]) == 0
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["a.de-2026-10.ndjson", "andere.txt", "b.de-2026-11.ndjson"]


def test_discard_refuses_path_tricks(tmp_path):
    (tmp_path / "x").mkdir()
    assert frog_state.main(["discard", "--dir", str(tmp_path / "x"), "--domain", "../a.de", "--run", "2026-11"]) == 1
    assert frog_state.main(["discard", "--dir", str(tmp_path / "x"), "--domain", "a.de", "--run", "../2026-11"]) == 1
