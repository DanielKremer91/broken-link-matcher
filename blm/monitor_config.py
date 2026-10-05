"""Read monitor.config.json and derive the monitor's paths from it.

The scripts the monitor may run without a permission prompt take no free paths
or recipients as arguments. Everything comes from the configuration: who gets
the mail, which competitors exist and where the files of a run live. That keeps
an unattended run from writing or sending anything the user did not set up.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

_RUN_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


class ConfigError(Exception):
    """monitor.config.json or an argument derived from it is unusable; message is user-facing German."""


def load_config(path: Path) -> dict:
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigError(f"Konfiguration {path} nicht lesbar: {exc}") from exc
    if not isinstance(cfg, dict):
        raise ConfigError(f"Konfiguration {path} ist kein JSON-Objekt.")
    return cfg


def current_run_id() -> str:
    return datetime.now().strftime("%Y-%m")


def check_run_id(run: str) -> str:
    if not _RUN_RE.match(run or ""):
        raise ConfigError(f"Lauf-Kennung muss das Format JJJJ-MM haben (ist: {run!r}).")
    return run


def output_root(cfg: dict, repo: Path) -> Path:
    """<repo>/<output_dir>; output_dir must be a plain relative folder inside the repo."""
    raw = str(cfg.get("output_dir") or "").strip()
    rel = Path(raw)
    if not raw or rel.is_absolute() or ".." in rel.parts:
        raise ConfigError(f"output_dir muss ein Ordner innerhalb des Repos sein (ist: {raw!r}).")
    return Path(repo) / rel


def check_competitor(cfg: dict, competitor: str) -> str:
    known = cfg.get("competitors")
    if not isinstance(known, list) or competitor not in known:
        raise ConfigError(f"{competitor!r} steht nicht in competitors der Konfiguration.")
    return competitor


def run_dir(cfg: dict, repo: Path, run: str) -> Path:
    return output_root(cfg, repo) / check_run_id(run)


def competitor_dir(cfg: dict, repo: Path, run: str, competitor: str) -> Path:
    return run_dir(cfg, repo, run) / check_competitor(cfg, competitor)


def kunde_slug(customer: str) -> str:
    """'Fressnapf GmbH' -> 'fressnapf-gmbh': lower case, umlauts spelled out, other characters as hyphens."""
    slug = re.sub(r"[^a-z0-9]+", "-", str(customer or "").lower().translate(_UMLAUTS)).strip("-")
    return slug or "kunde"
