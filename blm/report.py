"""Monthly report (plain text and HTML) for the customer: every open opportunity, new ones first.

An opportunity is a row with a suggestion that is no content gap and that the live
check did not mark as fixed. Wording is plain German for readers without SEO tools;
all explanations are fixed text, all values come from the run.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

from blm.export import format_snapshot
from blm.history import pair_key
from blm.models import MatchResult
from blm.pipeline import PipelineSummary

STATUS_LABELS = {
    "confirmed": "Link ist noch online",
    "unknown": "nicht automatisch prüfbar",
    "skipped": "nicht geprüft",
    "fixed": "erledigt",
}
MONTHS = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]


@dataclass
class Report:
    subject: str
    text: str
    html: str


def _unique(rows: list[MatchResult]) -> list[MatchResult]:
    """First row per normalised pair: http/https or www variants of one link appear once."""
    seen, out = set(), []
    for r in rows:
        key = pair_key(r.backlink)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _is_opportunity(r: MatchResult) -> bool:
    return bool(r.top) and not r.is_content_gap and r.verification != "fixed"


def all_opportunity_rows(results: list[MatchResult]) -> list[MatchResult]:
    """Every open opportunity of this run in priority order."""
    return _unique([r for r in results if _is_opportunity(r)])


def opportunity_rows(results: list[MatchResult], new_flags: list[bool]) -> list[MatchResult]:
    """Open opportunities that are new in this run, in priority order."""
    return _unique([r for r, new in zip(results, new_flags) if new and _is_opportunity(r)])


def gap_rows(results: list[MatchResult], new_flags: list[bool]) -> list[MatchResult]:
    return _unique([r for r, new in zip(results, new_flags)
                    if new and r.top and r.is_content_gap and r.verification != "fixed"])


def _score(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _dr(value: Optional[float]) -> str:
    return "unbekannt" if value is None else f"{value:.0f}"


def _one_line(value: Optional[str]) -> str:
    return " ".join((value or "").split())


def _month(run_id: str) -> str:
    """'2026-10' -> 'Oktober 2026'; anything else is shown as given."""
    try:
        year, month = run_id.split("-")
        return f"{MONTHS[int(month) - 1]} {int(year)}"
    except (ValueError, IndexError):
        return run_id


def _basis(r: MatchResult) -> str:
    rc = r.recovered
    if rc.source == "wayback":
        day = format_snapshot(rc.snapshot_timestamp)
        if len(day) == 10:
            day = f"{day[8:10]}.{day[5:7]}.{day[0:4]}"
        return f"Webarchiv, Stand {day}" if day else "Webarchiv"
    if rc.source == "fallback":
        return "nur Linktext und Umfeld (keine Archivkopie)"
    return "kein Inhalt"


def _attachment_label(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".xlsx") or lowered.endswith(".csv"):
        return f"vollständige Liste mit allen Details ({name})"
    if lowered.endswith(".md"):
        return f"Mail-Entwürfe an die verlinkenden Websites, nicht verschickt ({name})"
    return name


def explanations(customer: str) -> list[tuple[str, str]]:
    ours = f"von {customer}" if customer else "der eigenen Website"
    return [
        ("Verlinkende Website", "Die Seite, auf der der nicht mehr funktionierende Link steht. Ihr Betreiber ist der Ansprechpartner."),
        ("Stärke", "Domain Rating von Ahrefs, 0 bis 100. Je höher der Wert, desto wertvoller ist ein Link von dieser Website."),
        ("Nicht mehr erreichbare Seite", "Die Seite des Wettbewerbers, auf die der Link zeigt und die es nicht mehr gibt. Dahinter steht der ursprüngliche Linktext."),
        ("Passende Seite", f"Die Seite {ours}, die inhaltlich am besten zur nicht mehr erreichbaren Seite passt, darunter zwei Alternativen."),
        ("Passgenauigkeit", "Wert zwischen 0 und 1 aus dem inhaltlichen Vergleich beider Seiten. Je höher, desto besser passt die Seite."),
        ("Grundlage", "Woher der Inhalt der nicht mehr erreichbaren Seite stammt. Meist aus dem Webarchiv archive.org. Gibt es dort keine Kopie, stützt sich der Vergleich nur auf Linktext und Umfeld des Links und ist ungenauer."),
        ("Status", "Ergebnis der automatischen Prüfung am Tag des Berichts. \"Link ist noch online\" heißt: Die Website verlinkt weiterhin auf die nicht mehr erreichbare Seite."),
        ("Gemeldet seit", "Monat, in dem die Chance zum ersten Mal in diesem Bericht stand."),
    ]


def build_report(
    results: list[MatchResult],
    summary: PipelineSummary,
    new_flags: list[bool],
    *,
    competitor: str,
    customer: str = "",
    run_id: str = "",
    first_reported: Optional[list[str]] = None,
    attachments: Optional[list[str]] = None,
    history: bool = True,
) -> Report:
    """Report of all open opportunities. ``first_reported`` holds the run id of each row's first record."""
    since = dict(zip((id(r) for r in results), first_reported or [""] * len(results)))
    is_new = dict(zip((id(r) for r in results), new_flags))
    rows = all_opportunity_rows(results)
    new_rows = [r for r in rows if is_new.get(id(r), True)]
    old_rows = [r for r in rows if not is_new.get(id(r), True)]
    subject = f"Broken Link Chancen {customer}".strip()
    ours = customer or "die eigene Website"

    meta = " · ".join(p for p in (f"Stand: {_month(run_id)}" if run_id else "", f"Wettbewerber: {competitor}") if p)
    intro = (
        f"Andere Websites verlinken auf Seiten von {competitor}, die es nicht mehr gibt. Wer auf diese Links klickt, "
        f"landet auf einer Fehlerseite. Für jede dieser Seiten wurde ein passender Inhalt bei {ours} gefunden. "
        f"Ein kurzer, freundlicher Hinweis an die verlinkende Website kann daraus einen neuen Link für {ours} machen."
    )
    if not rows:
        overview = "Aktuell gibt es keine offenen Chancen."
    else:
        count = "1 Chance" if len(rows) == 1 else f"{len(rows)} Chancen"
        overview = f"{count}" + (f", davon {len(new_rows)} neu seit dem letzten Bericht." if history else ".")

    if history:
        sections = [("Neu seit dem letzten Bericht", new_rows, False),
                    ("Weiterhin offen", old_rows, True)]
    else:
        sections = [("Alle Chancen", rows, False)]

    details = [
        f"Ausgewertete Links: {summary.backlinks_ranked}",
        f"Inhalt der nicht mehr erreichbaren Seiten: {summary.snapshots} aus dem Webarchiv, "
        f"{summary.fallbacks} nur aus Linktext und Umfeld, {summary.no_text} ohne Inhalt",
    ]
    if summary.verified:
        details.append("Automatische Prüfung: " + ", ".join(
            f"{STATUS_LABELS.get(k, k)} {v}" for k, v in sorted(summary.verified.items())))

    # ---- plain text
    t = [subject, meta, "", intro, "", f"Auf einen Blick: {overview}"]
    for title, part, show_since in sections:
        if not part and show_since:
            continue
        t += ["", f"{title} ({len(part)})"]
        if not part:
            t.append("Keine.")
        for i, r in enumerate(part, start=1):
            bl = r.backlink
            anchor = _one_line(bl.anchor)
            t.append(f"{i}. {bl.url_from} (Stärke {_dr(bl.domain_rating)})")
            t.append(f"   Nicht mehr erreichbar: {bl.url_to}" + (f" (Linktext: {anchor})" if anchor else ""))
            t.append(f"   Passende Seite: {r.top[0].url} (Passgenauigkeit {_score(r.top[0].score)})")
            for m in r.top[1:]:
                t.append(f"   Alternative: {m.url} ({_score(m.score)})")
            t.append(f"   Grundlage: {_basis(r)} · Status: {STATUS_LABELS.get(r.verification, r.verification)}"
                     + (f" · gemeldet seit {_month(since.get(id(r)))}" if show_since and since.get(id(r)) else ""))
    t += ["", "Erklärung der Angaben"] + [f"- {name}: {text}" for name, text in explanations(customer)]
    if attachments:
        t += ["", "Im Anhang: " + "; ".join(_attachment_label(a) for a in attachments)]
    t += ["", "Technische Details"] + [f"- {d}" for d in details]
    if summary.errors:
        t += [f"- Hinweis zum Lauf: {e}" for e in summary.errors]
    text = "\n".join(t) + "\n"

    # ---- HTML
    e = html.escape
    h = [
        f'<h2 style="margin-bottom:4px">{e(subject)}</h2>',
        f'<p style="color:#666;margin-top:0">{e(meta)}</p>',
        f"<p>{e(intro)}</p>",
        f"<p><b>Auf einen Blick:</b> {e(overview)}</p>",
    ]
    for title, part, show_since in sections:
        if not part and show_since:
            continue
        h.append(f"<h3>{e(title)} ({len(part)})</h3>")
        if not part:
            h.append("<p>Keine.</p>")
            continue
        h.append('<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:13px">'
                 "<tr><th>Nr.</th><th>Verlinkende Website</th><th>Stärke</th><th>Nicht mehr erreichbare Seite</th>"
                 "<th>Passende Seite</th><th>Passgenauigkeit</th><th>Grundlage</th><th>Status</th>"
                 + ("<th>Gemeldet seit</th>" if show_since else "") + "</tr>")
        for i, r in enumerate(part, start=1):
            bl = r.backlink
            anchor = _one_line(bl.anchor)
            alternatives = "".join(f'<br><span style="color:#666">Alternative: {e(m.url)} ({e(_score(m.score))})</span>'
                                   for m in r.top[1:])
            h.append(
                f"<tr><td>{i}</td><td>{e(bl.url_from)}</td><td>{e(_dr(bl.domain_rating))}</td>"
                f"<td>{e(bl.url_to)}" + (f'<br><span style="color:#666">Linktext: {e(anchor)}</span>' if anchor else "")
                + f"</td><td><b>{e(r.top[0].url)}</b>{alternatives}</td><td>{e(_score(r.top[0].score))}</td>"
                f"<td>{e(_basis(r))}</td><td>{e(STATUS_LABELS.get(r.verification, r.verification))}</td>"
                + (f"<td>{e(_month(since.get(id(r)) or ''))}</td>" if show_since else "") + "</tr>"
            )
        h.append("</table>")
    h.append("<h3>Erklärung der Angaben</h3><ul>" + "".join(
        f"<li><b>{e(name)}:</b> {e(text)}</li>" for name, text in explanations(customer)) + "</ul>")
    if attachments:
        h.append("<p><b>Im Anhang:</b> " + e("; ".join(_attachment_label(a) for a in attachments)) + "</p>")
    h.append('<p style="color:#666;font-size:12px"><b>Technische Details</b><br>'
             + "<br>".join(e(d) for d in details)
             + "".join(f"<br>Hinweis zum Lauf: {e(x)}" for x in summary.errors) + "</p>")
    body = "\n".join(h)
    return Report(subject=subject, text=text,
                  html=f'<!doctype html><html><head><meta charset="utf-8"></head><body style="font-family:sans-serif">{body}</body></html>')
