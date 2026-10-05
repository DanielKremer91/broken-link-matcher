import json

import backlinks_check

HEADER = "url_from,url_to,anchor,domain_rating_source"


def write(tmp_path, rows):
    p = tmp_path / "broken-backlinks.csv"
    p.write_text("\n".join([HEADER] + rows) + "\n", encoding="utf-8")
    return p


ROWS = ["https://a.de/1,https://www.zooroyal.de/x,Anker,70", "https://b.de/2,https://zooroyal.de/y,Text,60",
        "https://c.de/3,https://ZOOROYAL.de/z,Link,50"]


def run(capsys, *args):
    rc = backlinks_check.main(list(args))
    out = capsys.readouterr()
    return rc, out.out + out.err


def test_matching_file_passes(tmp_path, capsys):
    rc, out = run(capsys, str(write(tmp_path, ROWS)), "--competitor", "zooroyal.de", "--rows", "3",
                  "--first", "https://a.de/1", "--last", "https://c.de/3")
    assert rc == 0 and json.loads(out)["rows"] == 3


def test_wrong_row_count_fails(tmp_path, capsys):
    rc, out = run(capsys, str(write(tmp_path, ROWS[:2])), "--competitor", "zooroyal.de", "--rows", "3",
                  "--first", "https://a.de/1", "--last", "https://b.de/2")
    assert rc == 1 and "3" in out and "2" in out


def test_changed_first_or_last_link_fails(tmp_path, capsys):
    p = write(tmp_path, ROWS)
    assert run(capsys, str(p), "--competitor", "zooroyal.de", "--rows", "3",
               "--first", "https://a.de/EINS", "--last", "https://c.de/3")[0] == 1
    rc, out = run(capsys, str(p), "--competitor", "zooroyal.de", "--rows", "3",
                  "--first", "https://a.de/1", "--last", "https://x.de/9")
    assert rc == 1 and "letzte" in out


def test_foreign_target_and_empty_file_fail(tmp_path, capsys):
    p = write(tmp_path, ROWS + ["https://d.de/4,https://fremd.de/q,x,10"])
    rc, out = run(capsys, str(p), "--competitor", "zooroyal.de", "--rows", "4",
                  "--first", "https://a.de/1", "--last", "https://d.de/4")
    assert rc == 1 and "zooroyal.de" in out
    rc, out = run(capsys, str(write(tmp_path, [])), "--competitor", "zooroyal.de", "--rows", "0",
                  "--first", "", "--last", "")
    assert rc == 1 and "keine" in out.lower()


def test_missing_file_fails(tmp_path, capsys):
    assert run(capsys, str(tmp_path / "fehlt.csv"), "--competitor", "k.de", "--rows", "1",
               "--first", "a", "--last", "b")[0] == 1
