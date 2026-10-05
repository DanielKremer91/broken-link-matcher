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
from frog_crawl_check import _on_domain
from blm.envfile import load_env_file
from blm.ingest.ahrefs_api import AhrefsError
from blm.console import use_utf8

def venv_python(repo: Path) -> Optional[Path]:
    """Interpreter of the repo's virtual environment on macOS/Linux or Windows."""
    for candidate in (repo / ".venv" / "bin" / "python", repo / ".venv" / "Scripts" / "python.exe"):
        if candidate.exists():
            return candidate
    return None


PROVIDER_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "ollama": None}
MAIL_METHODS = ("resend", "connector", "file")


def check(cfg: dict) -> list[tuple[bool, str, str]]:
    """(ok, what is checked, how to fix it) per item; the fix is plain German for beginners."""
    results: list[tuple[bool, str, str]] = []

    def add(ok: bool, text: str, fix: str = "") -> None:
        results.append((ok, text, fix))

    raw_repo = str(cfg.get("repo_path") or "").strip()
    repo = Path(raw_repo).expanduser()
    repo_ok = bool(raw_repo) and repo.is_absolute() and (repo / "cli.py").is_file()
    add(repo_ok, f"repo_path ist ein absoluter Pfad zum Repo mit cli.py ({raw_repo or 'leer'})",
        "In monitor.config.json bei repo_path den vollständigen Pfad zum Ordner broken-link-matcher eintragen, "
        "zum Beispiel /Users/name/broken-link-matcher.")
    if repo_ok:
        add(venv_python(repo) is not None, "Virtuelle Umgebung .venv ist eingerichtet",
            "Im Repo-Ordner ausführen: uv venv --python 3.11 .venv && uv pip install -r requirements.txt "
            "(ohne uv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt).")
        add((repo / ".env").is_file(), "Schlüsseldatei .env ist angelegt",
            "Im Repo-Ordner die Datei .env.example nach .env kopieren (macOS: cp -n .env.example .env && chmod 600 .env).")
        try:
            load_env_file(repo / ".env")
        except (OSError, UnicodeDecodeError):
            add(False, ".env ist lesbar (UTF-8)", ".env in einem Texteditor als reinen Text (UTF-8) speichern.")

    add(bool(str(cfg.get("customer") or "").strip()), "customer (Kundenname für den Betreff) ist gesetzt",
        "In monitor.config.json bei customer den Kundennamen eintragen, zum Beispiel Fressnapf.")
    add(bool(cfg.get("own_domain")), "own_domain ist gesetzt",
        "In monitor.config.json bei own_domain die eigene Domain eintragen, zum Beispiel fressnapf.de.")
    add(bool(str(cfg.get("output_dir") or "").strip()), "output_dir ist gesetzt",
        "In monitor.config.json bei output_dir einen Ordnernamen eintragen, zum Beispiel laeufe.")
    add(str(cfg.get("start_url", "")).startswith(("http://", "https://")), "start_url beginnt mit http(s)://",
        "In monitor.config.json bei start_url die vollständige Start-URL des Crawls eintragen, mit https://.")
    if cfg.get("own_domain") and cfg.get("start_url"):
        add(_on_domain(str(cfg["start_url"]), str(cfg["own_domain"])), "start_url gehört zu own_domain",
            "start_url und own_domain müssen dieselbe Website meinen, zum Beispiel https://www.fressnapf.de/magazin/ "
            "und fressnapf.de. Der Monitor verwendet nur Crawls der eigenen Domain.")

    frog = cfg.get("frog") or {}
    source = frog.get("embeddings_source", "custom_javascript")
    add(source in ("custom_javascript", "ai"),
        f"frog.embeddings_source ist custom_javascript oder ai (ist: {source})",
        "custom_javascript, wenn die Embeddings per Custom-JavaScript-Snippet entstehen; ai bei der eingebauten KI-Anbindung von Frog.")
    if frog.get("crawl", True):
        path = Path(str(frog.get("config_file", ""))).expanduser()
        add(bool(frog.get("config_file")) and path.is_file(), f"Frog-Konfiguration vorhanden ({path})",
            "In Screaming Frog über Konfiguration > Profile > Speichern unter... unter genau diesem Dateinamen im "
            "Ordner Downloads speichern. Danach place_frog_config.py --target <dieser Pfad> ausführen.")
    else:
        path = Path(str(frog.get("embeddings_file", ""))).expanduser()
        add(bool(frog.get("embeddings_file")) and path.is_file(), f"Frog-Embeddings-Export vorhanden ({path})",
            "Pfad bei frog.embeddings_file prüfen oder frog.crawl auf true setzen.")

    comps = cfg.get("competitors")
    comps_ok = isinstance(comps, list) and bool(comps) and all(isinstance(c, str) and c for c in comps)
    add(comps_ok, "competitors ist eine nicht leere Liste",
        'In monitor.config.json bei competitors die Wettbewerber eintragen, zum Beispiel ["zooroyal.de"].')
    if comps_ok:
        bad = [c for c in comps if "://" in c or "/" in c or c != c.strip().lower() or "." not in c]
        add(not bad, "Wettbewerber als Domain ohne Protokoll, Pfad und Großbuchstaben"
            + (f" (falsch: {', '.join(bad)})" if bad else ""),
            "Nur die Domain eintragen, klein geschrieben, ohne https:// und ohne Schrägstrich, zum Beispiel zooroyal.de.")

    emb = cfg.get("embedding") or {}
    provider = emb.get("provider")
    add(provider in PROVIDER_KEYS, f"embedding.provider ist openai, gemini oder ollama (ist: {provider})",
        "Den Anbieter eintragen, mit dem auch Screaming Frog die Embeddings erzeugt.")
    add(bool(emb.get("model")), "embedding.model ist gesetzt",
        "Das Modell eintragen, das auch Screaming Frog nutzt, zum Beispiel text-embedding-3-small.")
    var = PROVIDER_KEYS.get(provider)
    if var:
        add(bool(os.environ.get(var, "").strip()), f"{var} ist gesetzt (Umgebung oder .env)",
            f"Die Datei .env öffnen (open -e .env), den Schlüssel direkt hinter {var}= einfügen, speichern "
            "und das Fenster schließen. Den Schlüssel nie in den Chat schreiben.")

    drafts = cfg.get("drafts") or {}
    try:
        desc = build_ahrefs(cfg, "beispiel.de")["description"]
        add(True, f"Ahrefs-Filter gültig ({desc})")
    except (AhrefsError, KeyError, TypeError) as exc:
        add(False, f"Ahrefs-Filter gültig: {exc}",
            "Den Block ahrefs in monitor.config.json mit der Tabelle in docs/monatlicher-workflow.md abgleichen.")
    if drafts.get("enabled"):
        add(bool(str(drafts.get("sender", "")).strip()), "drafts.sender ist gesetzt",
            "Bei drafts.sender den Namen eintragen, mit dem die Textvorschläge unterschrieben werden.")

    mail = cfg.get("mail") or {}
    method = mail.get("method")
    add(method in MAIL_METHODS, f"mail.method ist resend, connector oder file (ist: {method})",
        "resend für Versand über Resend, connector für den verbundenen Outlook- oder Gmail-Connector, file ohne Versand.")
    if method in ("resend", "connector"):
        to = mail.get("to")
        add(isinstance(to, list) and bool(to) and all("@" in str(a) for a in to), "mail.to enthält Empfängeradressen",
            'Bei mail.to die Empfänger eintragen, zum Beispiel ["name@firma.de"].')
    if method == "resend":
        add(bool(os.environ.get("RESEND_API_KEY", "").strip()), "RESEND_API_KEY ist gesetzt (Umgebung oder .env)",
            "In Resend unter API keys einen Schlüssel mit Sending access anlegen und in .env hinter RESEND_API_KEY= einfügen.")
        sender = os.environ.get("RESEND_FROM", "").strip()
        add(bool(sender) and "@" in sender and "deine-domain.de" not in sender,
            "RESEND_FROM ist eine echte Absenderadresse (Umgebung oder .env)",
            "In .env hinter RESEND_FROM= einen Absender auf der in Resend verifizierten Domain eintragen, "
            "zum Beispiel Broken Link Monitor <monitor@deine-domain.de>.")
    return results


DEFAULT_FROG_DIR = Path("~/seo_spider_mcp_server")
KEY_NAMES = ("OPENAI_API_KEY", "GEMINI_API_KEY", "RESEND_API_KEY", "RESEND_FROM")
KEY_NOTES = {"OPENAI_API_KEY": " (bei OpenAI-Embeddings)", "GEMINI_API_KEY": " (nur bei Gemini-Embeddings)",
             "RESEND_API_KEY": " (nur bei Versand über Resend)", "RESEND_FROM": " (nur bei Versand über Resend)"}


def inventory(repo: Path, config: Path) -> list[tuple[bool, str]]:
    """What already exists, for the guided setup. Works without a config; never prints values."""
    items: list[tuple[bool, str]] = []
    items.append((venv_python(repo) is not None, "Virtuelle Umgebung .venv"))
    env = repo / ".env"
    items.append((env.is_file(), "Schlüsseldatei .env"))
    cfg: dict = {}
    if config.is_file():
        try:
            loaded = json.loads(config.read_text(encoding="utf-8"))
            cfg = loaded if isinstance(loaded, dict) else {}
            items.append((bool(cfg), f"Konfiguration {config.name}"))
        except (OSError, ValueError):
            items.append((False, f"Konfiguration {config.name} (vorhanden, aber kein gültiges JSON)"))
    else:
        items.append((False, f"Konfiguration {config.name}"))
    if env.is_file():
        try:
            load_env_file(env)
        except (OSError, UnicodeDecodeError):
            items.append((False, ".env lesbar"))
    for name in KEY_NAMES:
        items.append((bool(os.environ.get(name, "").strip()), f"{name} eingetragen{KEY_NOTES[name]}"))
    configured = (cfg.get("frog") or {}).get("config_file")
    if configured:
        frog_path = Path(str(configured)).expanduser()
        items.append((frog_path.is_file(), f"Frog-Konfiguration {frog_path}"))
    else:
        found = sorted(DEFAULT_FROG_DIR.expanduser().glob("broken-link-monitor*.seospiderconfig"))
        names = ", ".join(f.name for f in found)
        items.append((bool(found), "Frog-Konfigurationen im MCP-Ordner" + (f": {names} (passt eine zu dieser Website?)" if found else "")))
    out_dir = repo / str(cfg.get("output_dir") or "laeufe")
    histories = sorted(out_dir.glob("verlauf-*.json")) if out_dir.is_dir() else []
    items.append((bool(histories), "Frühere Läufe (Verlaufsdateien)"))
    return items


def main(argv: Optional[list[str]] = None) -> int:
    use_utf8()
    p = argparse.ArgumentParser(prog="check_setup.py", description="Einrichtung des Broken-Link-Monitors prüfen.")
    p.add_argument("--config", type=Path, default=Path(__file__).parent / "monitor.config.json")
    p.add_argument("--inventory", action="store_true",
                   help="Bestandsaufnahme für die Einrichtung: was ist schon da, was fehlt (auch ohne Konfiguration)")
    args = p.parse_args(argv)
    if args.inventory:
        for ok, text in inventory(Path(__file__).parent, args.config):
            print(("✓ vorhanden: " if ok else "○ fehlt: ") + text)
        return 0
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
    for ok, text, fix in results:
        print(("✓ " if ok else "✗ ") + text)
        if not ok and fix:
            print(f"  Lösung: {fix}")
    failed = sum(not ok for ok, _, _ in results)
    print("Alles bereit." if not failed else f"{failed} Punkt(e) offen.")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
