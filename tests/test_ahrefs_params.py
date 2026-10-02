import json

import ahrefs_params


def run(tmp_path, capsys, ahrefs=None, target="zooroyal.de"):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"ahrefs": ahrefs or {}}), encoding="utf-8")
    rc = ahrefs_params.main(["--config", str(cfg), "--target", target])
    out = capsys.readouterr()
    return rc, (json.loads(out.out) if rc == 0 else out.err)


def test_defaults_match_the_documented_mcp_call(tmp_path, capsys):
    rc, data = run(tmp_path, capsys)
    assert rc == 0
    mcp = data["mcp"]
    assert mcp["target"] == "zooroyal.de" and mcp["mode"] == "subdomains" and mcp["aggregation"] == "1_per_domain"
    assert mcp["order_by"] == "domain_rating_source:desc" and mcp["output"] == "csv" and mcp["limit"] == 100
    assert "traffic" not in mcp["select"].split(",")
    where = json.loads(mcp["where"])
    fields = json.dumps(where)
    for f in ("is_dofollow", "is_content", "is_spam", "http_code_target"):
        assert f in fields
    assert data["cli_args"] == ["--limit", "100", "--min-dr", "0", "--sort", "domain_rating"]
    assert data["description"] == "Dofollow · Content-Links · ohne Spam · nur 404/410"


def test_custom_filters(tmp_path, capsys):
    rc, data = run(tmp_path, capsys, {"limit": 250, "min_dr": 30, "dofollow_only": False, "exclude_spam": False,
                                      "include_traffic": True, "order_by": "traffic", "aggregation": "all"})
    assert rc == 0
    mcp = data["mcp"]
    assert mcp["limit"] == 250 and mcp["aggregation"] == "all" and mcp["order_by"] == "traffic:desc"
    assert "traffic" in mcp["select"].split(",")
    where = json.loads(mcp["where"])
    assert {"field": "domain_rating_source", "is": ["gte", 30]} in where["and"]
    assert "is_dofollow" not in mcp["where"] and "is_spam" not in mcp["where"]
    assert data["cli_args"] == ["--limit", "250", "--min-dr", "30", "--sort", "page_traffic", "--all-links"]


def test_all_filters_off_has_no_where(tmp_path, capsys):
    rc, data = run(tmp_path, capsys, {"dofollow_only": False, "content_only": False, "exclude_spam": False,
                                      "dead_only": False})
    assert rc == 0 and "where" not in data["mcp"]


def test_unknown_setting_and_bad_values_fail(tmp_path, capsys):
    assert "Unbekannte Ahrefs-Einstellungen" in run(tmp_path, capsys, {"sprache": "de"})[1]
    assert run(tmp_path, capsys, {"limit": 0})[0] == 1
    assert run(tmp_path, capsys, {"mode": "galaxie"})[0] == 1
    assert run(tmp_path, capsys, {"dofollow_only": "ja"})[0] == 1
    assert "include_traffic" in run(tmp_path, capsys, {"order_by": "traffic"})[1]
