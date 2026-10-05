import json

import frog_probe

VEC = ",".join(str(i / 100) for i in range(64))


def write(tmp_path, rows):
    p = tmp_path / "probe.ndjson"
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return p


def row(i, vec="", ctype="text/html; charset=utf-8", status="200"):
    return {"Address": f"https://a.de/{i}", "Content Type": ctype, "Status Code": status, "Ext 1": vec}


def test_ok_when_html_pages_have_vectors(tmp_path):
    p = write(tmp_path, [row(1, VEC), row(2, VEC), row(3, ctype="image/png")])
    assert frog_probe.probe(p, "Ext 1") == {"html_rows": 2, "with_vectors": 2, "dimension": 64, "verdict": "ok"}


def test_no_embeddings_after_enough_html_pages(tmp_path):
    p = write(tmp_path, [row(i) for i in range(12)] + [row(99, VEC, ctype="image/jpeg")])
    result = frog_probe.probe(p, "Ext 1")
    assert result["verdict"] == "keine_embeddings" and result["html_rows"] == 12


def test_too_little_data_when_few_html_pages(tmp_path):
    p = write(tmp_path, [row(1), row(2, ctype="text/css"), row(3, status="301")])
    assert frog_probe.probe(p, "Ext 1")["verdict"] == "zu_wenig_daten"


def test_field_detected_when_not_given(tmp_path):
    rows = [{"Address": f"https://a.de/{i}", "Embeddings Kunde 1": VEC} for i in range(3)]
    assert frog_probe.probe(write(tmp_path, rows))["verdict"] == "ok"


def test_cli_prints_json_and_handles_missing_file(tmp_path, capsys):
    p = write(tmp_path, [row(1, VEC)])
    assert frog_probe.main([str(p), "--field", "Ext 1"]) == 0
    assert json.loads(capsys.readouterr().out)["verdict"] == "ok"
    assert frog_probe.main([str(tmp_path / "fehlt.ndjson")]) == 1


def test_wide_export_of_builtin_ai_embeddings(tmp_path):
    p = tmp_path / "ai.csv"
    header = "url," + ",".join(f"embedding_{i}" for i in range(40))
    good = "https://a.de/1," + ",".join("0.1" for _ in range(40))
    empty = "https://a.de/2," + ",".join("" for _ in range(40))
    p.write_text("\n".join([header, good, good.replace("/1", "/3"), empty]), encoding="utf-8")
    r = frog_probe.probe(p)
    assert r["verdict"] == "ok" and r["with_vectors"] == 2 and r["dimension"] == 40


def test_domain_check_on_the_export(tmp_path):
    p = write(tmp_path, [row(1, VEC), row(2, VEC)])
    assert frog_probe.probe(p, "Ext 1", domain="a.de")["verdict"] == "ok"
    r = frog_probe.probe(p, "Ext 1", domain="fressnapf.de")
    assert r["verdict"] == "falsche_domain" and r["on_domain_share"] == 0.0


def test_load_reports_pages_like_the_matching_will_read_them(tmp_path, capsys):
    p = write(tmp_path, [row(1, VEC), row(2, VEC), row(3, "")])
    assert frog_probe.main([str(p), "--field", "Ext 1", "--load"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["pages"] == 2 and data["dimension"] == 64 and data["verdict"] == "ok"


def test_load_turns_an_unusable_export_into_keine_embeddings(tmp_path, capsys):
    p = write(tmp_path, [row(i, "kein vektor") for i in range(3)])
    assert frog_probe.main([str(p), "--field", "Ext 1", "--load"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["pages"] == 0 and data["verdict"] == "keine_embeddings"
