#!/usr/bin/env python
"""Find the Screaming Frog configuration the user just saved and move it to its place.

The user saves the file where it is easy (Downloads, which is not synced to iCloud)
under a given name; this script looks for it in Downloads, on the Desktop, in
Documents and the home folder, moves it
to the folder the Frog MCP can read and restricts its permissions, because the file
can contain an API key. It never reads or prints the file's content.

Exit codes: 0 moved or already in place, 1 nothing found, 2 several candidates.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Optional

SUFFIX = ".seospiderconfig"
DEFAULT_SEARCH = ("~/Downloads", "~/Desktop", "~/Documents", "~")


def find_candidates(target: Path, search_dirs: list[Path], max_age_minutes: int,
                    denied: Optional[list[Path]] = None) -> list[Path]:
    """Files named like the target (also with a typed path in front) win; else recent configs.

    Folders that exist but cannot be listed (macOS privacy protection) are collected in ``denied``.
    """
    named: list[Path] = []
    recent: list[Path] = []
    now = time.time()
    for folder in search_dirs:
        if not folder.is_dir():
            continue
        try:
            entries = sorted(p for p in folder.iterdir() if p.name.endswith(SUFFIX))
        except OSError:
            if denied is not None:
                denied.append(folder)
            continue
        for p in entries:
            if not p.is_file() or p.resolve() == target.resolve():
                continue
            if p.name == target.name or p.name.endswith(target.name):
                named.append(p)
            elif now - p.stat().st_mtime <= max_age_minutes * 60:
                recent.append(p)
    return named or recent


def place(source: Path, target: Path) -> Optional[Path]:
    """Move source to target; an existing target is kept as '<name>.vorher'. Returns the backup path."""
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if target.exists():
        backup = target.with_name(target.name + ".vorher")
        shutil.move(str(target), str(backup))
    shutil.move(str(source), str(target))
    target.chmod(0o600)
    return backup


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="place_frog_config.py",
                                description="Gespeicherte Frog-Konfiguration finden und an ihren Platz verschieben.")
    p.add_argument("--target", required=True, type=Path, help="Zielpfad, wie frog.config_file in monitor.config.json")
    p.add_argument("--source", type=Path, help="Datei direkt angeben statt suchen")
    p.add_argument("--search", nargs="*", type=Path, help="Suchordner (Standard: Downloads, Schreibtisch, Dokumente, Benutzerordner)")
    p.add_argument("--max-age", type=int, default=120, help="anders benannte Dateien nur, wenn höchstens so viele Minuten alt")
    args = p.parse_args(argv)
    target = args.target.expanduser()
    if args.source:
        source = args.source.expanduser()
        if not source.is_file():
            print(f"Nicht gefunden: {source}")
            return 1
        candidates = [source]
    else:
        dirs = [d.expanduser() for d in (args.search or [Path(d) for d in DEFAULT_SEARCH])]
        denied: list[Path] = []
        candidates = find_candidates(target, dirs, args.max_age, denied)
        for folder in denied:
            print(f"Kein Zugriff auf {folder}. Auf dem Mac fragt das System beim ersten Mal, ob Claude auf diesen Ordner "
                  "zugreifen darf. Bitte erlauben und erneut versuchen.")
    if not candidates:
        if target.is_file():
            print(f"Die Konfiguration liegt bereits am Ziel: {target}")
            return 0
        print(f"Keine gespeicherte Konfiguration gefunden. Bitte in Screaming Frog unter dem Namen {target.name} "
              "im Ordner Downloads speichern und erneut versuchen.")
        return 1
    if len(candidates) > 1:
        print("Mehrere Konfigurationsdateien gefunden. Welche ist die richtige?")
        for c in candidates:
            print(f"- {c}")
        print("Dann erneut mit --source <Datei> aufrufen.")
        return 2
    try:
        backup = place(candidates[0], target)
    except OSError as exc:
        print(f"Verschieben fehlgeschlagen: {exc}")
        return 1
    print(f"Konfiguration verschoben: {candidates[0]} -> {target}")
    if backup:
        print(f"Die bisherige Datei liegt als Sicherung unter {backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
