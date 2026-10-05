#!/usr/bin/env python
"""Small helpers that hide the differences between macOS and Windows.

The monitor calls the same command on both systems:

  oshelp.py keep-awake --hours 12   keep the computer from sleeping while a run works
  oshelp.py open <file>             open a file in the plain text editor
  oshelp.py info                    print system, home folder and the path of the venv python

keep-awake does not change any system setting. On macOS it runs caffeinate, on
Windows it asks the system to stay awake for as long as this process lives.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from blm.console import use_utf8

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def _run_and_wait(cmd: list[str]) -> int:
    return subprocess.call(cmd)


def _start(cmd: list[str]) -> None:
    subprocess.Popen(cmd)


def _set_windows_execution_state(flags: int) -> None:
    import ctypes
    ctypes.windll.kernel32.SetThreadExecutionState(flags)


def keep_awake(hours: float) -> int:
    seconds = int(hours * 3600)
    if sys.platform == "darwin":
        return _run_and_wait(["caffeinate", "-i", "-t", str(seconds)])
    if sys.platform.startswith("win"):
        _set_windows_execution_state(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        try:
            time.sleep(float(seconds))
        finally:
            _set_windows_execution_state(ES_CONTINUOUS)
        return 0
    print("Auf diesem System gibt es kein Schlafschutz-Kommando: kein Schlafschutz aktiv. Bitte den Standby für die Dauer des Laufs abschalten.")
    return 0


def open_file(path: Path) -> int:
    if sys.platform == "darwin":
        _start(["open", "-e", str(path)])
    elif sys.platform.startswith("win"):
        _start(["notepad", str(path)])
    else:
        _start(["xdg-open", str(path)])
    return 0


def venv_python_hint(platform: Optional[str] = None) -> str:
    platform = platform or sys.platform
    return ".venv\\Scripts\\python.exe" if platform.startswith("win") else ".venv/bin/python"


def main(argv: Optional[list[str]] = None) -> int:
    use_utf8()
    p = argparse.ArgumentParser(prog="oshelp.py", description="Hilfen, die auf macOS und Windows gleich aufgerufen werden.")
    sub = p.add_subparsers(dest="cmd", required=True)
    ka = sub.add_parser("keep-awake", help="Rechner wach halten, solange der Befehl läuft")
    ka.add_argument("--hours", type=float, default=12.0)
    op = sub.add_parser("open", help="Datei im Texteditor öffnen")
    op.add_argument("file", type=Path)
    sub.add_parser("info", help="System, Benutzerordner und Python der Umgebung ausgeben")
    args = p.parse_args(argv)
    if args.cmd == "keep-awake":
        return keep_awake(args.hours)
    if args.cmd == "open":
        if not args.file.exists():
            print(f"Nicht gefunden: {args.file}", file=sys.stderr)
            return 1
        return open_file(args.file)
    system = "macOS" if sys.platform == "darwin" else ("Windows" if sys.platform.startswith("win") else sys.platform)
    print(f"System: {system}")
    print(f"Benutzerordner: {Path.home()}")
    print(f"Downloads: {Path.home() / 'Downloads'}")
    print(f"Python der Umgebung: {venv_python_hint()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
