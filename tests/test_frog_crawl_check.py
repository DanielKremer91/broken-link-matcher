import json

import frog_crawl_check


def write(tmp_path, ok, broken, reason="Internet Disconnected"):
    rows = [{"Address": f"https://a.de/{i}", "Status Code": 200, "Status": None} for i in range(ok)]
    rows += [{"Address": f"https://a.de/x{i}", "Status Code": 0, "Status": reason} for i in range(broken)]
    p = tmp_path / "internal.ndjson"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def test_ok_below_five_percent(tmp_path):
    r = frog_crawl_check.crawl_health(write(tmp_path, 98, 2))
    assert r["verdict"] == "ok" and r["no_response"] == 2 and r["share"] == 0.02


def test_warning_and_reasons(tmp_path):
    r = frog_crawl_check.crawl_health(write(tmp_path, 90, 10))
    assert r["verdict"] == "warnung" and r["reasons"] == {"Internet Disconnected": 10}


def test_incomplete_above_thirty_percent(tmp_path):
    # the real test crawl of 2026-10-03: 450 of 1340 internal URLs without response
    assert frog_crawl_check.crawl_health(write(tmp_path, 890, 450))["verdict"] == "unvollstaendig"


def test_missing_status_column_and_file(tmp_path, capsys):
    p = tmp_path / "x.ndjson"
    p.write_text('{"Address": "https://a.de"}\n', encoding="utf-8")
    assert frog_crawl_check.main([str(p)]) == 1
    assert frog_crawl_check.main([str(tmp_path / "fehlt.ndjson")]) == 1
