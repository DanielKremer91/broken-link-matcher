#!/usr/bin/env python
"""Send the Broken Link Monitor report by e-mail through Resend.

Reads RESEND_API_KEY and RESEND_FROM from the environment or from a local .env
file (never from the command line). The key is never printed.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
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
    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.html and not args.text:
        parser.error("--html oder --text angeben")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
