#!/usr/bin/env python
"""Send this month's Broken Link Monitor report by e-mail through Resend.

Takes no recipients and no file paths. Recipients come from mail.to in
monitor.config.json, the files from the run folder of the given competitor:
bericht.html, bericht.md, ergebnis.xlsx and, if present, ergebnis-entwuerfe.md.
After sending, a marker (versendet.json) prevents a second mail in the same month.

RESEND_API_KEY and RESEND_FROM come from the environment or the local .env file
and are never printed.
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

from blm.console import use_utf8
from blm.envfile import load_env_file
from blm.mailer import MailError, send_resend
from blm.monitor_config import ConfigError, competitor_dir, current_run_id, load_config, run_dir

default_sleeper = time.sleep
REPO = Path(__file__).parent
MARKER_NAME = "versendet.json"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="send_report.py", description="Bericht des Monats per Resend an die Empfänger aus der Konfiguration schicken.",
        epilog="Empfänger und Dateien lassen sich nicht frei angeben. Schlüssel nur über RESEND_API_KEY und "
               "RESEND_FROM (Umgebung oder .env).")
    p.add_argument("--config", type=Path, default=REPO / "monitor.config.json")
    p.add_argument("--run", default=None, help="Lauf-Kennung JJJJ-MM (Standard: aktueller Monat)")
    what = p.add_mutually_exclusive_group(required=True)
    what.add_argument("--competitor", help="Bericht für diesen Wettbewerber aus competitors verschicken")
    what.add_argument("--error", action="store_true", help="fehler.md dieses Laufs als Fehlermeldung verschicken")
    p.add_argument("--resend", action="store_true", help="trotz Versandmerker erneut verschicken")
    p.add_argument("--env-file", type=Path, default=None, help="Schlüsseldatei (Standard: .env neben der Konfiguration)")
    return p


def read_marker(path: Path) -> Optional[dict]:
    if not path.is_file():
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


def _recipients(cfg: dict) -> list[str]:
    mail = cfg.get("mail") or {}
    if mail.get("method") != "resend":
        raise ConfigError("mail.method ist nicht resend. Dieses Skript verschickt nur über Resend.")
    to = mail.get("to")
    if not isinstance(to, list) or not to or not all(isinstance(a, str) and "@" in a for a in to):
        raise ConfigError("mail.to enthält keine Empfängeradressen.")
    return to


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Datei fehlt oder ist nicht lesbar: {path.name} ({exc})") from exc


def main(argv: Optional[list[str]] = None) -> int:
    use_utf8()
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        repo = args.config.resolve().parent
        run = args.run or current_run_id()
        to = _recipients(cfg)
        marker: Optional[Path] = None
        if args.error:
            folder = run_dir(cfg, repo, run)
            subject = f"Broken Link Monitor: Fehler im Lauf {run}"
            html, text, attachments = "", _read(folder / "fehler.md"), []
        else:
            folder = competitor_dir(cfg, repo, run, args.competitor)
            marker = folder / MARKER_NAME
            earlier = read_marker(marker)
            if earlier is not None and not args.resend:
                print(f"Bereits versendet am {earlier.get('sent_at', 'unbekannt')} an "
                      f"{', '.join(earlier.get('to', [])) or 'unbekannt'} (Resend-ID {earlier.get('id', 'unbekannt')}). "
                      "Kein erneuter Versand; mit --resend erzwingen.")
                return 0
            text = _read(folder / "bericht.md")
            html = _read(folder / "bericht.html")
            subject = (text.splitlines() or [""])[0].strip() or f"Broken Link Chancen {cfg.get('customer', '')}".strip()
            result = folder / "ergebnis.xlsx"
            if not result.is_file():
                raise ConfigError(f"Datei fehlt: ergebnis.xlsx in {folder}")
            drafts = folder / "ergebnis-entwuerfe.md"
            attachments = [result] + ([drafts] if drafts.is_file() else [])
    except ConfigError as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    try:
        load_env_file(args.env_file or repo / ".env")
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
        msg_id = send_resend(key, sender, to, subject, html, text, attachments, sleeper=default_sleeper)
    except MailError as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    print(f"Gesendet an {', '.join(to)} (Resend-ID {msg_id})")
    if marker is not None:
        try:
            write_marker(marker, to, subject, msg_id)
        except OSError as exc:
            print(f"Hinweis: Versandmerker konnte nicht geschrieben werden: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
