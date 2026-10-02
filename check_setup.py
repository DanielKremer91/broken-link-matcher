#!/usr/bin/env python
"""Check the Broken-Link-Monitor setup before a run. Prints only names, never secret values."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from ahrefs_params import build as build_ahrefs
from blm.envfile import load_env_file
from blm.ingest.ahrefs_api import AhrefsError

PROVIDER_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "ollama": None}
MAIL_METHODS = ("resend", "connector", "file")


def check(cfg: dict) -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []

    def add(ok: bool, text: str) -> None:
        results.append((ok, text))

    raw_repo = str(cfg.get("repo_path") or "").strip()
    repo = Path(raw_repo).expanduser()
    repo_ok = bool(raw_repo) and repo.is_absolute() and (repo / "cli.py").is_file()
    add(repo_ok, f"repo_path ist ein absoluter Pfad zum Repo mit cli.py ({raw_repo or 'leer'})")
    if repo_ok:
        add((repo / ".venv" / "bin" / "python").exists(), "Virtuelle Umgebung .venv ist eingerichtet")
        try:
            load_env_file(repo / ".env")
        except (OSError, UnicodeDecodeError):
            add(False, ".env ist lesbar (UTF-8)")

    add(bool(str(cfg.get("customer") or "").strip()), "customer (Kundenname für den Betreff) ist gesetzt")
    add(bool(cfg.get("own_domain")), "own_domain ist gesetzt")
    add(bool(str(cfg.get("output_dir") or "").strip()), "output_dir ist gesetzt")
    add(str(cfg.get("start_url", "")).startswith(("http://", "https://")), "start_url beginnt mit http(s)://")

    frog = cfg.get("frog") or {}
    source = frog.get("embeddings_source", "custom_javascript")
    add(source in ("custom_javascript", "ai"),
        f"frog.embeddings_source ist custom_javascript oder ai (ist: {source})")
    if frog.get("crawl", True):
        path = Path(str(frog.get("config_file", ""))).expanduser()
        add(bool(frog.get("config_file")) and path.is_file(), f"Frog-Konfiguration vorhanden ({path})")
    else:
        path = Path(str(frog.get("embeddings_file", ""))).expanduser()
        add(bool(frog.get("embeddings_file")) and path.is_file(), f"Frog-Embeddings-Export vorhanden ({path})")

    comps = cfg.get("competitors")
    comps_ok = isinstance(comps, list) and bool(comps) and all(isinstance(c, str) and c for c in comps)
    add(comps_ok, "competitors ist eine nicht leere Liste")
    if comps_ok:
        bad = [c for c in comps if "://" in c or "/" in c or c != c.strip().lower() or "." not in c]
        add(not bad, "Wettbewerber als Domain ohne Protokoll, Pfad und Großbuchstaben"
            + (f" (falsch: {', '.join(bad)})" if bad else ""))

    emb = cfg.get("embedding") or {}
    provider = emb.get("provider")
    add(provider in PROVIDER_KEYS, f"embedding.provider ist openai, gemini oder ollama (ist: {provider})")
    add(bool(emb.get("model")), "embedding.model ist gesetzt")
    var = PROVIDER_KEYS.get(provider)
    if var:
        add(bool(os.environ.get(var, "").strip()), f"{var} ist gesetzt (Umgebung oder .env)")

    drafts = cfg.get("drafts") or {}
    try:
        desc = build_ahrefs(cfg, "beispiel.de")["description"]
        add(True, f"Ahrefs-Filter gültig ({desc})")
    except (AhrefsError, KeyError, TypeError) as exc:
        add(False, f"Ahrefs-Filter gültig: {exc}")
    if drafts.get("enabled"):
        add(bool(str(drafts.get("sender", "")).strip()), "drafts.sender ist gesetzt")

    mail = cfg.get("mail") or {}
    method = mail.get("method")
    add(method in MAIL_METHODS, f"mail.method ist resend, connector oder file (ist: {method})")
    if method in ("resend", "connector"):
        to = mail.get("to")
        add(isinstance(to, list) and bool(to) and all("@" in str(a) for a in to), "mail.to enthält Empfängeradressen")
    if method == "resend":
        add(bool(os.environ.get("RESEND_API_KEY", "").strip()), "RESEND_API_KEY ist gesetzt (Umgebung oder .env)")
        sender = os.environ.get("RESEND_FROM", "").strip()
        add(bool(sender) and "@" in sender and "deine-domain.de" not in sender,
            "RESEND_FROM ist eine echte Absenderadresse (Umgebung oder .env)")
    return results


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="check_setup.py", description="Einrichtung des Broken-Link-Monitors prüfen.")
    p.add_argument("--config", type=Path, default=Path(__file__).parent / "monitor.config.json")
    args = p.parse_args(argv)
    if not args.config.is_file():
        print(f"✗ Konfiguration {args.config} nicht gefunden. Vorlage: .claude/skills/broken-link-monitor/config.example.json")
        return 1
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        if not isinstance(cfg, dict):
            raise ValueError("kein JSON-Objekt")
    except (OSError, ValueError) as exc:
        print(f"✗ Konfiguration {args.config} ist kein gültiges JSON: {exc}")
        return 1
    results = check(cfg)
    for ok, text in results:
        print(("✓ " if ok else "✗ ") + text)
    failed = sum(not ok for ok, _ in results)
    print("Alles bereit." if not failed else f"{failed} Punkt(e) offen.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
