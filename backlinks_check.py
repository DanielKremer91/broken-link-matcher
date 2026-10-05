#!/usr/bin/env python
"""Check a broken-backlinks CSV that Claude wrote from the Ahrefs MCP answer.

The MCP returns the rows as text and Claude writes them to a file. This script
catches rows that were lost or altered on the way: the row count, the first and
the last linking URL must match the MCP answer, and every dead URL must belong
to the competitor. Prints JSON on success; exit code 1 with a German message
otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from blm.console import use_utf8
from blm.ingest.backlinks_csv import detect_columns, read_table


def check(path: Path, competitor: str, rows: int, first: str, last: str) -> list[str]:
    df = read_table(path)
    problems: list[str] = []
    if len(df) == 0:
        return ["Die Datei enthält keine Datenzeilen."]
    mapping = detect_columns(df)
    if mapping.missing:
        return [f"Pflichtspalten fehlen: {', '.join(mapping.missing)}."]
    url_from = df[mapping.mapping["url_from"]].astype(str).str.strip()
    url_to = df[mapping.mapping["url_to"]].astype(str).str.strip()
    if len(df) != rows:
        problems.append(f"Zeilenzahl stimmt nicht: Die MCP-Antwort hatte {rows} Zeilen, die Datei hat {len(df)}.")
    if url_from.iloc[0] != first.strip():
        problems.append("Die erste linkgebende URL weicht von der MCP-Antwort ab.")
    if url_from.iloc[-1] != last.strip():
        problems.append("Die letzte linkgebende URL weicht von der MCP-Antwort ab.")
    foreign = int((~url_to.str.lower().str.contains(competitor.strip().lower(), regex=False)).sum())
    if foreign:
        problems.append(f"{foreign} tote URL(s) gehören nicht zu {competitor}.")
    return problems


def main(argv: Optional[list[str]] = None) -> int:
    use_utf8()
    p = argparse.ArgumentParser(prog="backlinks_check.py",
                                description="Geschriebene Broken-Backlinks-Datei gegen die MCP-Antwort prüfen.")
    p.add_argument("file", type=Path)
    p.add_argument("--competitor", required=True, help="Wettbewerber-Domain")
    p.add_argument("--rows", required=True, type=int, help="Zahl der Datenzeilen in der MCP-Antwort")
    p.add_argument("--first", required=True, help="url_from der ersten Datenzeile der MCP-Antwort")
    p.add_argument("--last", required=True, help="url_from der letzten Datenzeile der MCP-Antwort")
    args = p.parse_args(argv)
    try:
        problems = check(args.file, args.competitor, args.rows, args.first, args.last)
    except (OSError, ValueError) as exc:
        print(f"Abbruch: Datei nicht lesbar: {exc}", file=sys.stderr)
        return 1
    if problems:
        for line in problems:
            print(f"Abbruch: {line}", file=sys.stderr)
        return 1
    print(json.dumps({"rows": args.rows, "verdict": "ok"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
