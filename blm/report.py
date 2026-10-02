"""Monthly report (plain text and HTML): every open outreach opportunity, new ones first.

An opportunity is a row with a suggestion that is no content gap and that the live
check did not mark as fixed. New rows (not reported in an earlier run) come first,
then rows that are still open from earlier runs with the month of their first
report. Content gaps stay in the Excel file only.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Optional

from blm.export import format_snapshot
from blm.history import pair_key
from blm.models import MatchResult
from blm.pipeline import PipelineSummary

VERIFICATION_LABELS = {"confirmed": "bestätigt", "fixed": "erledigt", "unknown": "unbekannt", "skipped": "nicht geprüft"}


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


def _text_source(r: MatchResult) -> str:
    rc = r.recovered
    if rc.source == "wayback":
        day = format_snapshot(rc.snapshot_timestamp)
        return f"Wayback-Snapshot vom {day}" if day else "Wayback-Snapshot"
    reason = f" ({_one_line(rc.error)})" if rc.error else ""
    if rc.source == "fallback":
        return f"Ersatztext aus den Ahrefs-Angaben{reason}"
    return f"kein Text{reason}"


def _subject(competitor: str, total: int, new: int, history: bool) -> str:
    if total == 0:
        return f"Broken Link Monitor {competitor}: keine offenen Chancen"
    count = "1 Chance" if total == 1 else f"{total} Chancen"
    return f"Broken Link Monitor {competitor}: {count}" + (f", davon {new} neu" if history else "")


def build_report(
    results: list[MatchResult],
    summary: PipelineSummary,
    new_flags: list[bool],
    *,
    competitor: str,
    first_reported: Optional[list[str]] = None,
    attachments: Optional[list[str]] = None,
    history: bool = True,
) -> Report:
    """Report of all open opportunities. ``first_reported`` holds the run id of each row's first report."""
    since = dict(zip((id(r) for r in results), first_reported or [""] * len(results)))
    is_new = dict(zip((id(r) for r in results), new_flags))
    rows = all_opportunity_rows(results)
    new_rows = [r for r in rows if is_new.get(id(r), True)]
    old_rows = [r for r in rows if not is_new.get(id(r), True)]
    subject = _subject(competitor, len(rows), len(new_rows), history)

    stats = [f"Ausgewertete Backlinks: {summary.backlinks_ranked}"]
    stats.append(
        f"Text der toten Seiten: {summary.snapshots} aus der Wayback Machine, "
        f"{summary.fallbacks} mit Ersatztext aus Ahrefs-Angaben (kein nutzbarer Snapshot), {summary.no_text} ohne Text"
    )
    if summary.verified:
        stats.append("Live-Prüfung: " + ", ".join(
            f"{VERIFICATION_LABELS.get(k, k)} {v}" for k, v in sorted(summary.verified.items())))

    sections = [("Neu in diesem Lauf", new_rows, False), ("Weiterhin offen, bereits gemeldet", old_rows, True)]
    if not history:
        sections = [("Chancen", rows, False)]

    # ---- plain text
    t = [subject, "", *stats]
    for title, part, show_since in sections:
        if not part and title.startswith("Weiterhin"):
            continue
        t += ["", f"{title} ({len(part)}):"]
        if not part:
            t.append("Keine.")
        for i, r in enumerate(part, start=1):
            bl = r.backlink
            anchor = _one_line(bl.anchor)
            t.append(f"{i}. {bl.url_from} (DR {_dr(bl.domain_rating)})")
            t.append(f"   Tote URL: {bl.url_to}" + (f" (Anker: {anchor})" if anchor else ""))
            for n, m in enumerate(r.top, start=1):
                t.append(f"   Vorschlag {n}: {m.url} (Score {_score(m.score)})")
            t.append(f"   Text: {_text_source(r)} · Live-Prüfung: {VERIFICATION_LABELS.get(r.verification, r.verification)}"
                     + (f" · gemeldet seit {since.get(id(r))}" if show_since and since.get(id(r)) else ""))
    if summary.errors:
        t += ["", "Hinweise:"] + [f"- {e}" for e in summary.errors]
    if attachments:
        t += ["", "Dateien: " + ", ".join(attachments)]
    text = "\n".join(t) + "\n"

    # ---- HTML
    e = html.escape
    h = [f"<h2>{e(subject)}</h2>", "<ul>" + "".join(f"<li>{e(s)}</li>" for s in stats) + "</ul>"]
    for title, part, show_since in sections:
        if not part and title.startswith("Weiterhin"):
            continue
        h.append(f"<h3>{e(title)} ({len(part)})</h3>")
        if not part:
            h.append("<p>Keine.</p>")
            continue
        h.append('<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:13px">'
                 "<tr><th>#</th><th>Linkgeber</th><th>DR</th><th>Tote URL und Anker</th><th>Vorschläge (Score)</th>"
                 "<th>Text</th><th>Live-Prüfung</th>" + ("<th>Gemeldet seit</th>" if show_since else "") + "</tr>")
        for i, r in enumerate(part, start=1):
            bl = r.backlink
            anchor = _one_line(bl.anchor)
            suggestions = "<br>".join(f"{e(m.url)} ({e(_score(m.score))})" for m in r.top)
            h.append(
                f"<tr><td>{i}</td><td>{e(bl.url_from)}</td><td>{e(_dr(bl.domain_rating))}</td>"
                f"<td>{e(bl.url_to)}" + (f"<br><i>{e(anchor)}</i>" if anchor else "") + "</td>"
                f"<td>{suggestions}</td><td>{e(_text_source(r))}</td>"
                f"<td>{e(VERIFICATION_LABELS.get(r.verification, r.verification))}</td>"
                + (f"<td>{e(since.get(id(r)) or '')}</td>" if show_since else "") + "</tr>"
            )
        h.append("</table>")
    if summary.errors:
        h.append("<h3>Hinweise</h3><ul>" + "".join(f"<li>{e(x)}</li>" for x in summary.errors) + "</ul>")
    if attachments:
        h.append(f"<p>Dateien: {e(', '.join(attachments))}</p>")
    body = "\n".join(h)
    return Report(subject=subject, text=text,
                  html=f'<!doctype html><html><head><meta charset="utf-8"></head><body style="font-family:sans-serif">{body}</body></html>')
