#!/usr/bin/env python
"""Shared-Frog bookkeeping for the monthly monitor.

All setups on one computer share one Screaming Frog MCP instance, which can hold
only one crawl at a time. Two helpers keep runs apart and reruns honest:

  lock / unlock   a lock file in the Frog folder; another customer's run waits
                  instead of clearing or exporting a crawl that is not its own
  save-meta /     remembers with which settings this month's crawl was made, so a
  check-meta      crawl is only reused while start URL, Frog config and model match

Exit codes: 0 ok, 1 error or settings differ, 3 Frog is in use by another customer.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

LOCK_NAME = "frog-lock.json"
STALE_HOURS = 8


def _read(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def lock(folder: Path, customer: str, run: str) -> int:
    path = folder / LOCK_NAME
    current = _read(path) if path.is_file() else None
    if current and current.get("customer") != customer:
        age_hours = (time.time() - path.stat().st_mtime) / 3600
        if age_hours < STALE_HOURS:
            print(f"Screaming Frog ist belegt: Lauf für {current.get('customer')} seit {current.get('started', 'unbekannt')}. "
                  "Später erneut versuchen.")
            return 3
    folder.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"customer": customer, "run": run,
                                "started": datetime.now().isoformat(timespec="seconds")}, ensure_ascii=False),
                    encoding="utf-8")
    print(f"Screaming Frog reserviert für {customer}.")
    return 0


def unlock(folder: Path, customer: str) -> int:
    path = folder / LOCK_NAME
    current = _read(path) if path.is_file() else None
    if path.is_file() and (current is None or current.get("customer") == customer):
        path.unlink()
        print("Reservierung aufgehoben.")
    return 0


def crawl_settings(config_path: Path) -> dict:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    frog = cfg.get("frog") or {}
    frog_file = Path(str(frog.get("config_file") or "")).expanduser()
    return {
        "start_url": cfg.get("start_url"),
        "frog_config_file": str(frog_file),
        "frog_config_saved": int(frog_file.stat().st_mtime) if frog_file.is_file() else None,
        "embeddings_source": frog.get("embeddings_source", "custom_javascript"),
        "custom_js_field": frog.get("custom_js_field") or "",
        "embedding_model": (cfg.get("embedding") or {}).get("model"),
    }


LABELS = {"start_url": "Start-URL", "frog_config_file": "Pfad der Frog-Konfiguration",
          "frog_config_saved": "Frog-Konfiguration (neu gespeichert)", "embeddings_source": "Embedding-Weg",
          "custom_js_field": "Embedding-Feld", "embedding_model": "Embedding-Modell"}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="frog_state.py", description="Frog-Reservierung und Crawl-Einstellungen des Monitors.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("lock", "unlock"):
        sp = sub.add_parser(name)
        sp.add_argument("--dir", required=True, type=Path, help="Ordner broken-link-monitor im Frog-Basisverzeichnis")
        sp.add_argument("--customer", required=True)
        if name == "lock":
            sp.add_argument("--run", default="")
    for name in ("save-meta", "check-meta"):
        sp = sub.add_parser(name)
        sp.add_argument("--config", required=True, type=Path, help="monitor.config.json")
        sp.add_argument("--meta", required=True, type=Path, help="Meta-Datei neben dem Embedding-Export")
    args = p.parse_args(argv)
    try:
        if args.cmd == "lock":
            return lock(args.dir.expanduser(), args.customer, args.run)
        if args.cmd == "unlock":
            return unlock(args.dir.expanduser(), args.customer)
        settings = crawl_settings(args.config)
        if args.cmd == "save-meta":
            args.meta.parent.mkdir(parents=True, exist_ok=True)
            args.meta.write_text(json.dumps(settings, ensure_ascii=False, indent=1), encoding="utf-8")
            print("Crawl-Einstellungen gemerkt.")
            return 0
        stored = _read(args.meta) if args.meta.is_file() else None
        if stored is None:
            print("Keine gemerkten Crawl-Einstellungen: der vorhandene Crawl wird nicht wiederverwendet.")
            return 1
        changed = [LABELS[k] for k in settings if stored.get(k) != settings[k]]
        if changed:
            print("Seit dem Crawl geändert: " + ", ".join(changed) + ". Es wird neu gecrawlt.")
            return 1
        print("Crawl-Einstellungen unverändert.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
