#!/usr/bin/env python
"""Send the Broken Link Monitor report by e-mail through Resend.

Reads RESEND_API_KEY and RESEND_FROM from the environment or from a local .env
file (never from the command line). The key is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from blm.envfile import load_env_file
from blm.mailer import MailError, send_resend

default_sleeper = time.sleep


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="send_report.py", description="Bericht per Resend verschicken.",
                                epilog="Schlüssel nur über RESEND_API_KEY und RESEND_FROM (Umgebung oder .env).")
    p.add_argument("--to", required=True, action="append", help="Empfänger, mehrfach möglich")
    p.add_argument("--subject", required=True)
    p.add_argument("--html", type=Path, help="HTML-Datei für den Mailtext")
    p.add_argument("--text", type=Path, help="Textdatei für den Mailtext (Klartext-Variante)")
    p.add_argument("--attach", type=Path, action="append", default=[], help="Anhang, mehrfach möglich")
    p.add_argument("--env-file", type=Path, default=Path(__file__).parent / ".env")
    p.add_argument("--marker", type=Path,
                   help="Versandmerker (JSON): existiert er, wird nicht erneut verschickt; nach dem Versand wird er geschrieben")
    p.add_argument("--resend", action="store_true", help="trotz vorhandenem Versandmerker erneut verschicken")
    return p


def read_marker(path: Optional[Path]) -> Optional[dict]:
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}  # unreadable marker still means: something was sent before


def write_marker(path: Path, to: list[str], subject: str, msg_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"sent_at": datetime.now().isoformat(timespec="seconds"), "to": to,
                                "subject": subject, "id": msg_id}, ensure_ascii=False, indent=1), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.html and not args.text:
        parser.error("--html oder --text angeben")
    earlier = read_marker(args.marker)
    if earlier is not None and not args.resend:
        print(f"Bereits versendet am {earlier.get('sent_at', 'unbekannt')} an {', '.join(earlier.get('to', [])) or 'unbekannt'} "
              f"(Resend-ID {earlier.get('id', 'unbekannt')}). Kein erneuter Versand; mit --resend erzwingen.")
        return 0
    try:
        load_env_file(args.env_file)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Abbruch: Schlüsseldatei nicht lesbar: {exc}", file=sys.stderr)
        return 1
    key = os.environ.get("RESEND_API_KEY", "").strip()
    sender = os.environ.get("RESEND_FROM", "").strip()
    if not key:
        print("Abbruch: Umgebungsvariable RESEND_API_KEY ist nicht gesetzt.", file=sys.stderr)
        return 1
    if not sender:
        print("Abbruch: Umgebungsvariable RESEND_FROM ist nicht gesetzt (z. B. Monitor <reports@deine-domain.de>).",
              file=sys.stderr)
        return 1
    try:
        html = args.html.read_text(encoding="utf-8") if args.html else ""
        text = args.text.read_text(encoding="utf-8") if args.text else ""
    except OSError as exc:
        print(f"Abbruch: Mailtext nicht lesbar: {exc}", file=sys.stderr)
        return 1
    try:
        msg_id = send_resend(key, sender, args.to, args.subject, html, text, args.attach, sleeper=default_sleeper)
    except MailError as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    print(f"Gesendet an {', '.join(args.to)} (Resend-ID {msg_id})")
    if args.marker:
        try:
            write_marker(args.marker, args.to, args.subject, msg_id)
        except OSError as exc:
            print(f"Hinweis: Versandmerker konnte nicht geschrieben werden: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
