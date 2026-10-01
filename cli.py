#!/usr/bin/env python
"""Broken Link Matcher on the command line.

Runs the same workflow as the Streamlit app without a browser, so Claude Code
or a shell script can drive it. Keys come from environment variables only:
OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL (default http://localhost:11434).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

from blm.cache import JsonCache
from blm.embeddings import DEFAULT_EMBED_MODELS, PROVIDERS, EmbeddingError, make_provider
from blm.export import results_to_dataframe, to_csv_bytes, to_xlsx_bytes
from blm.outreach import DEFAULT_CHAT_MODELS
from blm.pipeline import ChatConfig, PipelineConfig, PipelineError, PipelineResult, run_pipeline, summary_to_dict
from blm.ranking import SORT_FIELDS

default_sleeper = time.sleep
ENV_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Broken Link Matcher: tote Wettbewerber-URLs mit eigenen Seiten matchen (ohne Oberfläche).",
        epilog="Schlüssel nur über Umgebungsvariablen: OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL.",
    )
    p.add_argument("--frog", required=True, type=Path, help="Screaming-Frog-Embeddings-Export (CSV)")
    p.add_argument("--backlinks", required=True, type=Path, help="Broken-Backlinks-Export (CSV/XLSX)")
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
    p.add_argument("--pause", type=float, default=1.0, help="Sekunden Pause nach jedem Wayback-Abruf")
    p.add_argument("--contact", help="Kontakt (Mail oder URL) für den User-Agent")
    p.add_argument("--verify", action="store_true", help="Live prüfen: Ziel noch 404, Link noch vorhanden")
    p.add_argument("--drafts", action="store_true", help="Mail-Entwürfe erzeugen (braucht --sender und --domain)")
    p.add_argument("--sender", default="", help="Absender-Name für Mail-Entwürfe")
    p.add_argument("--domain", default="", help="eigene Domain für Mail-Entwürfe")
    p.add_argument("--chat-model", help="Chat-Modell für Entwürfe (Standard je Anbieter)")
    p.add_argument("--drafts-out", type=Path, help="Markdown-Datei für die Mail-Entwürfe (Standard: <Name von --out>-entwuerfe.md neben --out)")
    p.add_argument("--cache-dir", type=Path, default=Path(__file__).parent / ".cache")
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


def write_output(result: PipelineResult, out_path: Path, drafts_path: Optional[Path]) -> None:
    if drafts_path is not None:
        lines = ["# Mail-Entwürfe", ""]
        for key, text in result.drafts.items():
            url_from, url_to = key.split("|", 1)
            url_to = re.sub(r"#\d+$", "", url_to)  # occurrence suffix for repeated pairs
            lines += [f"## {url_from}", "", f"Tote URL: {url_to}", "", text, ""]
        drafts_path.parent.mkdir(parents=True, exist_ok=True)
        drafts_path.write_text("\n".join(lines), encoding="utf-8")  # drafts first: they cost money
    df = results_to_dataframe(result.results)
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
        f"Wayback: {s.snapshots} Snapshots, {s.fallbacks} Fallbacks, {s.no_text} ohne Text",
        f"Treffer: {s.matched}, Content-Gaps: {s.content_gaps}, nicht gematcht: {s.unmatched}",
    ]
    if s.verified:
        lines.append("Verifikation: " + ", ".join(f"{k} {v}" for k, v in sorted(s.verified.items())))
    if s.drafts:
        lines.append(f"Mail-Entwürfe: {s.drafts}")
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
    if args.drafts and (not args.sender.strip() or not args.domain.strip()):
        print("Mail-Entwürfe brauchen --sender und --domain.", file=sys.stderr)
        return 1

    drafts_out: Optional[Path] = None
    if args.drafts:
        drafts_out = args.drafts_out or args.out.with_name(f"{args.out.stem}-entwuerfe.md")
    targets = [args.out] + ([drafts_out] if drafts_out else [])
    try:
        for t in targets:
            t.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"Abbruch: Ausgabeordner kann nicht angelegt werden: {exc}", file=sys.stderr)
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
    try:
        write_output(result, args.out, drafts_out)
    except OSError as exc:
        print(f"Abbruch: Ergebnisdatei konnte nicht geschrieben werden: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = summary_to_dict(result.summary)
        payload["output"] = str(args.out)
        if drafts_out:
            payload["drafts_output"] = str(drafts_out)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in summary_lines(result.summary):
            print(line)
        print(f"Ergebnis: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
