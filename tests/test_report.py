from blm.models import BrokenBacklink, Match, MatchResult, RecoveredContent
from blm.pipeline import PipelineSummary
from blm.report import all_opportunity_rows, build_report, opportunity_rows


def row(i, *, gap=False, verification="confirmed", top=True, dr=50.0, source="wayback"):
    bl = BrokenBacklink(url_from=f"https://linkgeber{i}.de/artikel", url_to=f"https://zooroyal.de/tot{i}",
                        anchor=f"Anker {i}", domain_rating=dr)
    rc = RecoveredContent(url_to=bl.url_to, text="t", source=source,
                          snapshot_timestamp="20160809120000" if source == "wayback" else None,
                          error=None if source == "wayback" else "Kein Snapshot mit Status 200")
    r = MatchResult(backlink=bl, recovered=rc)
    if top:
        r.top = [Match(url=f"https://fressnapf.de/magazin/{i}", score=0.81234),
                 Match(url=f"https://fressnapf.de/magazin/{i}-b", score=0.7),
                 Match(url=f"https://fressnapf.de/magazin/{i}-c", score=0.65)]
    r.is_content_gap = gap
    r.verification = verification
    r.priority = i
    return r


def summary():
    return PipelineSummary(own_pages=10, dimension=3, backlinks_total=5, backlinks_ranked=5, matched=3,
                           snapshots=4, fallbacks=1)


def test_opportunities_exclude_fixed_gaps_and_unmatched():
    rows = [row(1), row(2, verification="fixed"), row(3, gap=True), row(4, top=False), row(5, verification="unknown")]
    assert [r.priority for r in all_opportunity_rows(rows)] == [1, 5]
    assert [r.priority for r in opportunity_rows(rows, [False, True, True, True, True])] == [5]


def test_first_run_lists_everything_as_new():
    rep = build_report([row(1), row(2)], summary(), [True, True], competitor="zooroyal.de")
    assert rep.subject == "Broken Link Monitor zooroyal.de: 2 Chancen, davon 2 neu"
    assert "Neu in diesem Lauf (2)" in rep.text and "Weiterhin offen" not in rep.text


def test_next_run_lists_known_rows_with_month_after_new_ones():
    rows = [row(1), row(2), row(3)]
    rep = build_report(rows, summary(), [False, True, False], competitor="k.de",
                       first_reported=["2026-10", "2026-11", "2026-10"])
    assert rep.subject.endswith("3 Chancen, davon 1 neu")
    text = rep.text
    assert text.index("Neu in diesem Lauf (1)") < text.index("linkgeber2.de") < text.index("Weiterhin offen")
    assert text.index("Weiterhin offen, bereits gemeldet (2)") < text.index("linkgeber1.de")
    assert "gemeldet seit 2026-10" in text
    assert "<th>Gemeldet seit</th>" in rep.html and "<td>2026-10</td>" in rep.html


def test_no_new_rows_still_sends_full_list():
    rep = build_report([row(1)], summary(), [False], competitor="k.de", first_reported=["2026-10"])
    assert rep.subject.endswith("1 Chance, davon 0 neu")
    assert "Neu in diesem Lauf (0):\nKeine." in rep.text and "linkgeber1.de" in rep.text


def test_nothing_open():
    rep = build_report([row(1, verification="fixed")], summary(), [True], competitor="k.de")
    assert rep.subject.endswith("keine offenen Chancen")


def test_all_three_suggestions_and_text_source_are_listed():
    rep = build_report([row(1), row(2, source="fallback")], summary(), [True, True], competitor="k.de")
    for body in (rep.text, rep.html):
        assert "https://fressnapf.de/magazin/1-c" in body and "0,81" in body and "0,65" in body
        assert "Wayback-Snapshot vom 2016-08-09" in body
        assert "Ersatztext aus den Ahrefs-Angaben (Kein Snapshot mit Status 200)" in body


def test_content_gaps_are_not_in_the_mail():
    rep = build_report([row(1), row(2, gap=True)], summary(), [True, True], competitor="k.de")
    assert "tot2" not in rep.text and "tot2" not in rep.html and "Content-Gap" not in rep.text


def test_without_history_one_plain_list():
    rep = build_report([row(1), row(2)], summary(), [True, True], competitor="k.de", history=False)
    assert rep.subject == "Broken Link Monitor k.de: 2 Chancen"
    assert "Neu in diesem Lauf" not in rep.text and "Chancen (2):" in rep.text


def test_stats_explain_fallbacks():
    rep = build_report([row(1)], summary(), [True], competitor="k.de")
    assert "4 aus der Wayback Machine, 1 mit Ersatztext aus Ahrefs-Angaben (kein nutzbarer Snapshot)" in rep.text


def test_html_escapes_third_party_text():
    r = row(1)
    r.backlink.anchor = "<script>alert(1)</script>"
    r.backlink.url_from = "https://x.de/?a=<b>"
    rep = build_report([r], summary(), [True], competitor="k.de")
    assert "<script>" not in rep.html and "&lt;script&gt;" in rep.html
    assert "<b>" not in rep.html


def test_errors_and_files_appear():
    s = summary()
    s.errors.append("Wayback-Fehler bei 2 URLs")
    rep = build_report([row(1)], s, [True], competitor="k.de", attachments=["ergebnis.xlsx", "entwuerfe.md"])
    assert "Wayback-Fehler bei 2 URLs" in rep.text
    assert "ergebnis.xlsx" in rep.text and "entwuerfe.md" in rep.html


def test_unknown_dr_and_multiline_anchor():
    r = row(1, dr=None)
    r.backlink.anchor = "Zeile eins\n\tZeile zwei"
    rep = build_report([r], summary(), [True], competitor="k.de")
    assert "DR unbekannt" in rep.text and "(Anker: Zeile eins Zeile zwei)" in rep.text


def test_http_and_https_variants_of_one_pair_are_listed_once():
    a, b = row(1), row(2)
    b.backlink.url_from = a.backlink.url_from.replace("https://", "http://")
    b.backlink.url_to = a.backlink.url_to
    assert len(all_opportunity_rows([a, b])) == 1


def test_html_declares_utf8():
    assert '<meta charset="utf-8">' in build_report([row(1)], summary(), [True], competitor="k.de").html
