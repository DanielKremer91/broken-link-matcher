#!/usr/bin/env python
"""Broken Link Matcher on the command line.

Runs the same workflow as the Streamlit app without a browser, so Claude Code
or a shell script can drive it. Keys come from environment variables only:
OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL (default http://localhost:11434),
optionally filled from a local .env file that never overrides the shell.

For the monthly monitor: --seen-file remembers reported pairs, --report writes
a short text and HTML report of the new opportunities.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional

from blm.cache import JsonCache
from blm.embeddings import DEFAULT_EMBED_MODELS, PROVIDERS, EmbeddingError, make_provider
from blm.envfile import load_env_file
from blm.export import MAIL_HIDDEN_COLUMNS, results_to_dataframe, to_csv_bytes, to_xlsx_bytes
from blm.history import HistoryError, current_run_id, load_seen, mark_new, pair_key, record_reported, save_seen
from blm.outreach import DEFAULT_CHAT_MODELS
from blm.pipeline import ChatConfig, PipelineConfig, PipelineError, PipelineResult, run_pipeline, summary_to_dict
from blm.ranking import SORT_FIELDS
from blm.report import all_opportunity_rows, build_report, gap_rows, opportunity_rows

default_sleeper = time.sleep
ENV_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}
DEFAULT_ENV_FILE = Path(__file__).parent / ".env"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Broken Link Matcher: tote Wettbewerber-URLs mit eigenen Seiten matchen (ohne Oberfläche).",
        epilog="Schlüssel nur über Umgebungsvariablen oder .env: OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL.",
    )
    p.add_argument("--frog", required=True, type=Path, help="Screaming-Frog-Embeddings-Export (CSV/TSV/TXT/XLSX)")
    p.add_argument("--backlinks", required=True, type=Path, help="Broken-Backlinks-Export (CSV/TSV/TXT/XLSX)")
    p.add_argument("--provider", choices=PROVIDERS, default="openai", help="Embedding-Anbieter wie im Frog")
    p.add_argument("--model", help="Embedding-Modell wie im Frog (Standard je Anbieter)")
    p.add_argument("--out", required=True, type=Path, help="Ergebnisdatei .xlsx oder .csv")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--min-dr", type=float, default=0.0)
    p.add_argument("--sort", choices=SORT_FIELDS, default="domain_rating")
    p.add_argument("--all-links", action="store_true", help="auch Nofollow- und Nicht-Content-Links")
    p.add_argument("--threshold", type=float, default=0.5, help="Content-Gap unterhalb dieses Scores")
    p.add_argument("--no-fallback", action="store_true", help="Zeilen ohne Snapshot nicht matchen")
    p.add_argument("--max-chars", type=int, default=12000)
    p.add_argument("--pause", type=float, default=1.0, help="Sekunden Pause nach jedem Abruf aus der Wayback Machine")
    p.add_argument("--contact", help="Kontakt (Mail oder URL) für den User-Agent")
    p.add_argument("--verify", action="store_true", help="Live prüfen: Ziel noch 404, Link noch vorhanden")
    p.add_argument("--drafts", action="store_true", help="Mail-Entwürfe erzeugen (braucht --sender und --domain)")
    p.add_argument("--sender", default="", help="Absender-Name für Mail-Entwürfe")
    p.add_argument("--domain", default="", help="eigene Domain für Mail-Entwürfe")
    p.add_argument("--chat-model", help="Chat-Modell für Entwürfe (Standard je Anbieter)")
    p.add_argument("--drafts-out", type=Path, help="Markdown-Datei für die Mail-Entwürfe (Standard: <Name von --out>-entwuerfe.md neben --out)")
    p.add_argument("--cache-dir", type=Path, default=Path(__file__).parent / ".cache")
    p.add_argument("--seen-file", type=Path, help="Verlaufsdatei (JSON): markiert neue Zeilen und merkt sich die im Bericht gemeldeten")
    p.add_argument("--run-id", help="Kennung des Laufs, Standard aktueller Monat JJJJ-MM; ein zweiter Lauf mit gleicher Kennung liefert denselben Bericht")
    p.add_argument("--report", type=Path,
                   help="Bericht als .md oder .txt, dazu eine .html-Datei daneben; die Ergebnisdatei ist dann der "
                        "Mailanhang und enthält keine internen Spalten (Priorität, Rang Linkwert, Traffic, Content-Gap)")
    p.add_argument("--competitor", help="Name des Wettbewerbers im Bericht (Standard: häufigster Host der toten URLs)")
    p.add_argument("--customer", default="", help="Kundenname für Betreff und Text des Berichts, z. B. Fressnapf")
    p.add_argument("--note", action="append", default=[],
                   help="Hinweis zum Lauf für den Bericht, z. B. ein unvollständiger Crawl; mehrfach möglich")
    p.add_argument("--env-file", type=Path, help="Datei mit KEY=Wert-Zeilen für Schlüssel (Standard: .env im Repo)")
    p.add_argument("--json", action="store_true", help="Zusammenfassung als JSON auf stdout")
    p.add_argument("--quiet", action="store_true", help="keinen Fortschritt auf stderr")
    return p


def resolve_credentials(provider: str) -> tuple[Optional[str], Optional[str]]:
    """(api_key, base_url) from the environment; raises PipelineError with the variable name."""
    if provider == "ollama":
        return None, os.environ.get("OLLAMA_URL") or "http://localhost:11434"
    var = ENV_KEYS[provider]
    key = os.environ.get(var, "").strip()
    if not key:
        raise PipelineError(f"Umgebungsvariable {var} ist nicht gesetzt.")
    return key, None


def guess_competitor(result: PipelineResult) -> str:
    hosts = Counter()
    for r in result.results:
        try:
            host = urlparse(r.backlink.url_to).netloc.lower()
        except ValueError:
            continue
        if host:
            hosts[host[4:] if host.startswith("www.") else host] += 1
    return hosts.most_common(1)[0][0] if hosts else "Wettbewerber"


def write_output(result: PipelineResult, out_path: Path, drafts_path: Optional[Path],
                 new_flags: Optional[list[bool]] = None, first_reported: Optional[list[str]] = None,
                 hide: tuple[str, ...] = ()) -> None:
    if drafts_path is not None:
        lines = ["# Mail-Entwürfe", ""]
        for key, text in result.drafts.items():
            url_from, url_to = key.split("|", 1)
            url_to = re.sub(r"#\d+$", "", url_to)  # occurrence suffix for repeated pairs
            lines += [f"## {url_from}", "", f"Tote URL: {url_to}", "", text, ""]
        drafts_path.parent.mkdir(parents=True, exist_ok=True)
        drafts_path.write_text("\n".join(lines), encoding="utf-8")  # drafts first: they cost money
    df = results_to_dataframe(result.results, new_flags, first_reported, hide=hide)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".xlsx":
        out_path.write_bytes(to_xlsx_bytes(df))
    else:
        out_path.write_bytes(to_csv_bytes(df))


def summary_lines(summary) -> list[str]:
    s = summary
    lines = [
        f"Eigene Seiten: {s.own_pages} (Dimension {s.dimension})",
        f"Backlinks: {s.backlinks_total} geladen, {s.backlinks_ranked} nach Filter",
        f"Wayback Machine: {s.snapshots} Snapshots, {s.fallbacks} Fallbacks, {s.no_text} ohne Text",
        f"Treffer: {s.matched}, Content-Gaps: {s.content_gaps}, nicht gematcht: {s.unmatched}",
    ]
    if s.verified:
        lines.append("Verifikation: " + ", ".join(f"{k} {v}" for k, v in sorted(s.verified.items())))
    if s.drafts:
        lines.append(f"Mail-Entwürfe: {s.drafts}")
    if getattr(s, "excel_dates_repaired", 0) > 0:
        lines.append(f"Hinweis: {s.excel_dates_repaired} Excel-Datumswerte zurückgerechnet")
    for e in s.errors:
        lines.append(f"Fehler: {e}")
    return lines


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.out.is_dir() or (args.drafts_out and args.drafts_out.is_dir()):
        print("Abbruch: --out/--drafts-out zeigt auf ein Verzeichnis.", file=sys.stderr)
        return 1
    if args.out.suffix.lower() not in (".xlsx", ".csv"):
        parser.error("--out muss auf .xlsx oder .csv enden")
    if args.pause < 0:
        parser.error("--pause darf nicht negativ sein")
    if args.limit < 1:
        parser.error("--limit muss mindestens 1 sein")
    if args.max_chars < 1000:
        parser.error("--max-chars muss mindestens 1000 sein")
    if not 0 <= args.min_dr <= 100:
        parser.error("--min-dr muss zwischen 0 und 100 liegen")
    if args.report and args.report.suffix.lower() not in (".md", ".txt"):
        parser.error("--report muss auf .md oder .txt enden")
    if args.drafts and (not args.sender.strip() or not args.domain.strip()):
        print("Mail-Entwürfe brauchen --sender und --domain.", file=sys.stderr)
        return 1

    drafts_out: Optional[Path] = None
    if args.drafts:
        drafts_out = args.drafts_out or args.out.with_name(f"{args.out.stem}-entwuerfe.md")
    report_html = args.report.with_suffix(".html") if args.report else None
    targets = [args.out] + ([drafts_out] if drafts_out else []) + ([args.report] if args.report else [])
    try:
        for t in targets:
            t.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Abbruch: Ausgabeordner kann nicht angelegt werden: {exc}", file=sys.stderr)
        return 1

    try:
        load_env_file(args.env_file or DEFAULT_ENV_FILE)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Abbruch: Schlüsseldatei nicht lesbar: {exc}", file=sys.stderr)
        return 1
    run_id = (args.run_id or current_run_id()).strip()
    seen: Optional[dict] = None
    if args.seen_file:
        try:
            seen = load_seen(args.seen_file)
        except HistoryError as exc:
            print(f"Abbruch: {exc}", file=sys.stderr)
            return 1

    def progress(stage: str, done: int, total: int) -> None:
        if not args.quiet:
            print(f"[{stage}] {done}/{total}", file=sys.stderr, end="\r" if done < total else "\n")

    try:
        api_key, base_url = resolve_credentials(args.provider)
        model = args.model or DEFAULT_EMBED_MODELS[args.provider]
        provider = make_provider(args.provider, model, api_key=api_key, base_url=base_url)
        chat = (ChatConfig(args.provider, args.chat_model or DEFAULT_CHAT_MODELS[args.provider], api_key, base_url)
                if args.drafts else None)
        cfg = PipelineConfig(
            frog_path=args.frog, backlinks_path=args.backlinks,
            dofollow_only=not args.all_links, content_only=not args.all_links,
            min_dr=args.min_dr, sort_by=args.sort, limit=args.limit, max_chars=args.max_chars,
            threshold=args.threshold, match_fallback=not args.no_fallback,
            verify=args.verify, drafts=args.drafts, sender_name=args.sender, own_domain=args.domain,
            contact=args.contact, pause=args.pause,
        )
        result = run_pipeline(cfg, provider, chat=chat, cache=JsonCache(args.cache_dir),
                              sleeper=default_sleeper, progress=progress)
    except (PipelineError, EmbeddingError) as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    result.summary.errors.extend(n.strip() for n in args.note if n.strip())
    new_flags = mark_new(result.results, seen or {}, run_id)
    # every open opportunity is in the report, content gaps are in the Excel file; both are
    # remembered so "Neu" stays meaningful, known pairs keep the run of their first record
    recorded = all_opportunity_rows(result.results) + [r for r in result.results
                                                       if r.top and r.is_content_gap and r.verification != "fixed"]
    updated = record_reported(seen or {}, recorded, run_id)
    first_reported = [updated.get(pair_key(r.backlink), {}).get("since", "") for r in result.results]
    report = None
    try:
        # with --report the result file is the attachment of the customer mail: no internal columns
        write_output(result, args.out, drafts_out, new_flags if seen is not None else None,
                     first_reported if seen is not None else None,
                     hide=MAIL_HIDDEN_COLUMNS if args.report else ())
        if args.report:
            attachments = [args.out.name] + ([drafts_out.name] if drafts_out else [])
            report = build_report(result.results, result.summary, new_flags,
                                  competitor=args.competitor or guess_competitor(result), attachments=attachments,
                                  customer=args.customer.strip(), run_id=run_id,
                                  first_reported=first_reported, history=seen is not None)
            args.report.write_text(report.text, encoding="utf-8")
            report_html.write_text(report.html, encoding="utf-8")
        if seen is not None:
            # Only rows that appear in the report are remembered, tagged with the run of their first report.
            # Fixed, gap and unmatched rows stay open; a rerun with the same id rebuilds the same report.
            save_seen(args.seen_file, updated)
    except OSError as exc:
        print(f"Abbruch: Ergebnisdatei konnte nicht geschrieben werden: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = summary_to_dict(result.summary)
        payload["output"] = str(args.out)
        if drafts_out:
            payload["drafts_output"] = str(drafts_out)
        payload["run_id"] = run_id
        if seen is not None:
            payload["new_rows"] = sum(new_flags)
        payload["opportunities"] = len(all_opportunity_rows(result.results))
        payload["new_opportunities"] = len(opportunity_rows(result.results, new_flags))
        payload["new_content_gaps"] = len(gap_rows(result.results, new_flags))
        if report:
            payload.update(report=str(args.report), report_html=str(report_html), report_subject=report.subject)
        if args.seen_file:
            payload["seen_file"] = str(args.seen_file)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in summary_lines(result.summary):
            print(line)
        if seen is not None:
            print(f"Offene Chancen: {len(all_opportunity_rows(result.results))}, "
                  f"davon neu: {len(opportunity_rows(result.results, new_flags))}")
        print(f"Ergebnis: {args.out}")
        if report:
            print(f"Bericht: {args.report} und {report_html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
