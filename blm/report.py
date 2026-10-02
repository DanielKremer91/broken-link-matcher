"""Short monthly report (plain text and HTML) listing new outreach opportunities."""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

from blm.models import MatchResult
from blm.pipeline import PipelineSummary

VERIFICATION_LABELS = {"confirmed": "bestätigt", "fixed": "erledigt", "unknown": "unbekannt", "skipped": "nicht geprüft"}


@dataclass
class Report:
    subject: str
    text: str
    html: str


def opportunity_rows(results: list[MatchResult], new_flags: list[bool]) -> list[MatchResult]:
    """New rows with a suggestion that are no content gap and not already fixed, in priority order."""
    return [r for r, new in zip(results, new_flags)
            if new and r.top and not r.is_content_gap and r.verification != "fixed"]


def gap_rows(results: list[MatchResult], new_flags: list[bool]) -> list[MatchResult]:
    return [r for r, new in zip(results, new_flags) if new and r.is_content_gap and r.verification != "fixed"]


def _score(value: float) -> str:
    return f"{value:.2f}".replace(".", ",")


def _dr(value: Optional[float]) -> str:
    return "" if value is None else f"{value:.0f}"


def _count_label(n: int) -> str:
    if n == 0:
        return "keine neuen Chancen"
    return "1 neue Chance" if n == 1 else f"{n} neue Chancen"


def build_report(
    results: list[MatchResult],
    summary: PipelineSummary,
    new_flags: list[bool],
    *,
    competitor: str,
    top_n: int = 15,
    attachments: Optional[list[str]] = None,
) -> Report:
    opps = opportunity_rows(results, new_flags)
    gaps = gap_rows(results, new_flags)
    shown = opps[:top_n]
    rest = len(opps) - len(shown)
    subject = f"Broken Link Monitor {competitor}: {_count_label(len(opps))}"
    new_total = sum(new_flags)
    stats = [
        f"Ausgewertete Backlinks: {summary.backlinks_ranked}, davon neu seit dem letzten Lauf: {new_total}",
        f"Wayback: {summary.snapshots} Snapshots, {summary.fallbacks} Fallbacks, {summary.no_text} ohne Text",
    ]
    if summary.verified:
        stats.append("Live-Prüfung: " + ", ".join(
            f"{VERIFICATION_LABELS.get(k, k)} {v}" for k, v in sorted(summary.verified.items())))

    # ---- plain text
    t = [subject, "", *stats, ""]
    if shown:
        t.append("Neue Chancen (nach Priorität):")
        for i, r in enumerate(shown, start=1):
            bl = r.backlink
            t += [
                f"{i}. {bl.url_from} (DR {_dr(bl.domain_rating)})",
                f"   Tote URL: {bl.url_to}" + (f" (Anker: {bl.anchor})" if bl.anchor else ""),
                f"   Vorschlag: {r.top[0].url} (Score {_score(r.top[0].score)})",
                f"   Live-Prüfung: {VERIFICATION_LABELS.get(r.verification, r.verification)}",
            ]
        if rest > 0:
            t.append(f"... und {rest} weitere in der Ergebnisdatei.")
    else:
        t.append("Keine neuen Chancen seit dem letzten Lauf.")
    if gaps:
        t += ["", "Neue Content-Gaps (kein passender eigener Inhalt):"]
        t += [f"- {r.backlink.url_to} (verlinkt von {r.backlink.url_from})" for r in gaps[:top_n]]
    if summary.errors:
        t += ["", "Hinweise:"] + [f"- {e}" for e in summary.errors]
    if attachments:
        t += ["", "Anhänge: " + ", ".join(attachments)]
    text = "\n".join(t) + "\n"

    # ---- HTML
    e = html.escape
    h = [f"<h2>{e(subject)}</h2>", "<ul>" + "".join(f"<li>{e(s)}</li>" for s in stats) + "</ul>"]
    if shown:
        h.append("<h3>Neue Chancen</h3>")
        h.append('<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:14px">'
                 "<tr><th>#</th><th>Linkgeber</th><th>DR</th><th>Tote URL</th><th>Anker</th><th>Vorschlag</th>"
                 "<th>Score</th><th>Live-Prüfung</th></tr>")
        for i, r in enumerate(shown, start=1):
            bl = r.backlink
            h.append(
                f"<tr><td>{i}</td><td>{e(bl.url_from)}</td><td>{e(_dr(bl.domain_rating))}</td>"
                f"<td>{e(bl.url_to)}</td><td>{e(bl.anchor or '')}</td><td>{e(r.top[0].url)}</td><td>{e(_score(r.top[0].score))}</td>"
                f"<td>{e(VERIFICATION_LABELS.get(r.verification, r.verification))}</td></tr>"
            )
        h.append("</table>")
        if rest > 0:
            h.append(f"<p>... und {rest} weitere in der Ergebnisdatei.</p>")
    else:
        h.append("<p>Keine neuen Chancen seit dem letzten Lauf.</p>")
    if gaps:
        h.append("<h3>Neue Content-Gaps</h3><ul>" + "".join(
            f"<li>{e(r.backlink.url_to)} (verlinkt von {e(r.backlink.url_from)})</li>" for r in gaps[:top_n]) + "</ul>")
    if summary.errors:
        h.append("<h3>Hinweise</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in summary.errors) + "</ul>")
    if attachments:
        h.append(f"<p>Anhänge: {e(', '.join(attachments))}</p>")
    body = "\n".join(h)
    return Report(subject=subject, text=text, html=f'<!doctype html><html><body style="font-family:sans-serif">{body}</body></html>')
