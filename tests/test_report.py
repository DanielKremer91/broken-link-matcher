from blm.models import BrokenBacklink, Match, MatchResult, RecoveredContent
from blm.pipeline import PipelineSummary
from blm.report import build_report, opportunity_rows


def row(i, *, gap=False, verification="confirmed", top=True, dr=50.0):
    bl = BrokenBacklink(url_from=f"https://linkgeber{i}.de/artikel", url_to=f"https://zooroyal.de/tot{i}",
                        anchor=f"Anker {i}", domain_rating=dr)
    r = MatchResult(backlink=bl, recovered=RecoveredContent(url_to=bl.url_to, text="t", source="wayback"))
    if top:
        r.top = [Match(url=f"https://fressnapf.de/magazin/{i}", score=0.81234)]
    r.is_content_gap = gap
    r.verification = verification
    r.priority = i
    return r


def summary():
    return PipelineSummary(own_pages=10, dimension=3, backlinks_total=5, backlinks_ranked=5, matched=3)


def test_opportunities_exclude_fixed_gaps_and_unmatched():
    rows = [row(1), row(2, verification="fixed"), row(3, gap=True), row(4, top=False), row(5, verification="unknown")]
    flags = [True] * 5
    assert [r.priority for r in opportunity_rows(rows, flags)] == [1, 5]


def test_opportunities_only_new_rows():
    rows = [row(1), row(2)]
    assert [r.priority for r in opportunity_rows(rows, [False, True])] == [2]


def test_subject_counts_new_opportunities():
    rep = build_report([row(1), row(2)], summary(), [True, True], competitor="zooroyal.de")
    assert rep.subject == "Broken Link Monitor zooroyal.de: 2 neue Chancen"


def test_subject_singular_and_none():
    assert build_report([row(1)], summary(), [True], competitor="k.de").subject.endswith("1 neue Chance")
    rep = build_report([row(1)], summary(), [False], competitor="k.de")
    assert rep.subject.endswith("keine neuen Chancen")
    assert "Keine neuen Chancen" in rep.text


def test_text_and_html_list_link_giver_dead_url_and_suggestion():
    rep = build_report([row(1)], summary(), [True], competitor="zooroyal.de")
    for body in (rep.text, rep.html):
        assert "https://linkgeber1.de/artikel" in body
        assert "https://zooroyal.de/tot1" in body
        assert "https://fressnapf.de/magazin/1" in body
        assert "0,81" in body


def test_content_gaps_listed_separately():
    rep = build_report([row(1), row(2, gap=True)], summary(), [True, True], competitor="k.de")
    assert "Content-Gaps" in rep.text and "https://zooroyal.de/tot2" in rep.text


def test_top_n_limits_listing_but_not_count():
    rows = [row(i) for i in range(1, 8)]
    rep = build_report(rows, summary(), [True] * 7, competitor="k.de", top_n=3)
    assert "7 neue Chancen" in rep.subject
    assert "linkgeber3.de" in rep.text and "linkgeber4.de" not in rep.text
    assert "4 weitere" in rep.text


def test_html_escapes_third_party_text():
    r = row(1)
    r.backlink.anchor = "<script>alert(1)</script>"
    r.backlink.url_from = "https://x.de/?a=<b>"
    rep = build_report([r], summary(), [True], competitor="k.de")
    assert "<script>" not in rep.html and "&lt;script&gt;" in rep.html
    assert "<b>" not in rep.html


def test_errors_and_attachment_hint_appear():
    s = summary()
    s.errors.append("Wayback-Fehler bei 2 URLs")
    rep = build_report([row(1)], s, [True], competitor="k.de", attachments=["ergebnis.xlsx", "entwuerfe.md"])
    assert "Wayback-Fehler bei 2 URLs" in rep.text
    assert "ergebnis.xlsx" in rep.text and "entwuerfe.md" in rep.html


def test_without_history_wording_drops_neu():
    rep = build_report([row(1), row(2)], summary(), [True, True], competitor="k.de", history=False)
    assert rep.subject == "Broken Link Monitor k.de: 2 Chancen"
    assert "neu seit dem letzten Lauf" not in rep.text
    rep = build_report([], summary(), [], competitor="k.de", history=False)
    assert rep.subject.endswith("keine Chancen")


def test_unknown_dr_and_multiline_anchor():
    r = row(1, dr=None)
    r.backlink.anchor = "Zeile eins\n\tZeile zwei"
    rep = build_report([r], summary(), [True], competitor="k.de")
    assert "DR unbekannt" in rep.text
    assert "(Anker: Zeile eins Zeile zwei)" in rep.text


def test_content_gaps_are_capped_with_rest_note():
    rows = [row(i, gap=True) for i in range(1, 6)]
    rep = build_report(rows, summary(), [True] * 5, competitor="k.de", top_n=2)
    assert "tot2" in rep.text and "tot3" not in rep.text and "3 weitere" in rep.text


def test_html_declares_utf8():
    assert '<meta charset="utf-8">' in build_report([row(1)], summary(), [True], competitor="k.de").html
