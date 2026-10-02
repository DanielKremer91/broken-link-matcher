#!/usr/bin/env python
"""Check the Broken-Link-Monitor setup before a run. Prints only names, never secret values."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from blm.envfile import load_env_file

PROVIDER_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "ollama": None}
MAIL_METHODS = ("resend", "connector", "file")


def check(cfg: dict) -> list[tuple[bool, str]]:
    results: list[tuple[bool, str]] = []

    def add(ok: bool, text: str) -> None:
        results.append((ok, text))

    repo = Path(str(cfg.get("repo_path", ""))).expanduser()
    repo_ok = (repo / "cli.py").is_file()
    add(repo_ok, f"repo_path zeigt auf das Repo mit cli.py ({repo})")
    if repo_ok:
        add((repo / ".venv" / "bin" / "python").exists(), "Virtuelle Umgebung .venv ist eingerichtet")
        try:
            load_env_file(repo / ".env")
        except (OSError, UnicodeDecodeError):
            add(False, ".env ist lesbar (UTF-8)")

    add(bool(cfg.get("own_domain")), "own_domain ist gesetzt")
    add(str(cfg.get("start_url", "")).startswith(("http://", "https://")), "start_url beginnt mit http(s)://")

    frog = cfg.get("frog") or {}
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
        bad = [c for c in comps if "://" in c or "/" in c.strip("/")]
        add(not bad, "Wettbewerber als Domain ohne Protokoll und Pfad" + (f" (falsch: {', '.join(bad)})" if bad else ""))

    emb = cfg.get("embedding") or {}
    provider = emb.get("provider")
    add(provider in PROVIDER_KEYS, f"embedding.provider ist openai, gemini oder ollama (ist: {provider})")
    add(bool(emb.get("model")), "embedding.model ist gesetzt")
    var = PROVIDER_KEYS.get(provider)
    if var:
        add(bool(os.environ.get(var, "").strip()), f"{var} ist gesetzt (Umgebung oder .env)")

    drafts = cfg.get("drafts") or {}
    if drafts.get("enabled"):
        add(bool(str(drafts.get("sender", "")).strip()), "drafts.sender ist gesetzt")

    mail = cfg.get("mail") or {}
    method = mail.get("method")
    add(method in MAIL_METHODS, f"mail.method ist resend, connector oder file (ist: {method})")
    if method in ("resend", "connector"):
        to = mail.get("to")
        add(isinstance(to, list) and bool(to) and all("@" in str(a) for a in to), "mail.to enthält Empfängeradressen")
    if method == "resend":
        for name in ("RESEND_API_KEY", "RESEND_FROM"):
            add(bool(os.environ.get(name, "").strip()), f"{name} ist gesetzt (Umgebung oder .env)")
    return results


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="check_setup.py", description="Einrichtung des Broken-Link-Monitors prüfen.")
    p.add_argument("--config", type=Path, default=Path(__file__).parent / "monitor.config.json")
    args = p.parse_args(argv)
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
