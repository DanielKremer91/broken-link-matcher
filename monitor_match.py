#!/usr/bin/env python
"""Run the matching for one competitor of the monthly monitor.

A thin, fixed entry point around cli.py. It takes no output paths and no
identities: files live in the run folder, settings come from
monitor.config.json. Only the Frog export of the own site is passed in, because
it lies in the Frog folder outside the repo; it is only read.

Prints the same JSON summary as `cli.py --json`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import cli
from ahrefs_params import build as build_ahrefs
from blm.console import use_utf8
from blm.ingest.ahrefs_api import AhrefsError
from blm.monitor_config import ConfigError, competitor_dir, current_run_id, load_config, output_root

REPO = Path(__file__).parent


def build_cli_args(cfg: dict, repo: Path, run: str, competitor: str, frog: Path, notes: list[str]) -> list[str]:
    folder = competitor_dir(cfg, repo, run, competitor)
    emb = cfg.get("embedding") or {}
    argv = [
        "--frog", str(frog),
        "--backlinks", str(folder / "broken-backlinks.csv"),
        "--provider", str(emb.get("provider") or "openai"),
        "--model", str(emb.get("model") or ""),
        *build_ahrefs(cfg, competitor)["cli_args"],
        "--out", str(folder / "ergebnis.xlsx"),
        "--seen-file", str(output_root(cfg, repo) / f"verlauf-{competitor}.json"),
        "--run-id", run,
        "--report", str(folder / "bericht.md"),
        "--competitor", competitor,
        "--customer", str(cfg.get("customer") or ""),
        "--env-file", str(repo / ".env"),
        "--json", "--quiet",
    ]
    if cfg.get("verify"):
        argv.append("--verify")
    drafts = cfg.get("drafts") or {}
    if drafts.get("enabled"):
        argv += ["--drafts", "--sender", str(drafts.get("sender") or ""), "--domain", str(cfg.get("own_domain") or "")]
    if str(cfg.get("contact") or "").strip():
        argv += ["--contact", str(cfg["contact"]).strip()]
    for note in notes:
        if note.strip():
            argv += ["--note", note.strip()]
    return argv


def main(argv: Optional[list[str]] = None) -> int:
    use_utf8()
    p = argparse.ArgumentParser(prog="monitor_match.py",
                                description="Matching des Monitors für einen Wettbewerber, Einstellungen aus der Konfiguration.")
    p.add_argument("--config", type=Path, default=REPO / "monitor.config.json")
    p.add_argument("--run", default=None, help="Lauf-Kennung JJJJ-MM (Standard: aktueller Monat)")
    p.add_argument("--competitor", required=True, help="Wettbewerber aus competitors")
    p.add_argument("--frog", required=True, type=Path, help="Embedding-Export der eigenen Seiten aus Schritt 1")
    p.add_argument("--note", action="append", default=[], help="Hinweis zum Lauf für den Bericht, mehrfach möglich")
    p.add_argument("--cache-dir", type=Path, default=None, help=argparse.SUPPRESS)
    args = p.parse_args(argv)
    try:
        cfg = load_config(args.config)
        repo = args.config.resolve().parent
        run = args.run or current_run_id()
        cli_args = build_cli_args(cfg, repo, run, args.competitor, args.frog, args.note)
    except (ConfigError, AhrefsError) as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    backlinks = Path(cli_args[cli_args.index("--backlinks") + 1])
    if not backlinks.is_file():
        print(f"Abbruch: {backlinks.name} fehlt im Laufordner {backlinks.parent}. Erst Schritt 2 ausführen.", file=sys.stderr)
        return 1
    if args.cache_dir:
        cli_args += ["--cache-dir", str(args.cache_dir)]
    return cli.main(cli_args)


if __name__ == "__main__":
    sys.exit(main())
