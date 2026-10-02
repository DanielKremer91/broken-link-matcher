"""Remember which backlink pairs earlier runs already reported, so a monthly run lists only new ones."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from blm.models import BrokenBacklink, MatchResult


class HistoryError(Exception):
    """The seen-file exists but cannot be used; message is user-facing German."""


def pair_key(bl: BrokenBacklink) -> str:
    return f"{(bl.url_from or '').strip()}|{(bl.url_to or '').strip()}"


def load_seen(path: Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise HistoryError(f"Verlaufsdatei {path} ist nicht lesbar: {exc}") from exc
    keys = data.get("keys") if isinstance(data, dict) else None
    if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
        raise HistoryError(f"Verlaufsdatei {path} hat ein unerwartetes Format.")
    return set(keys)


def save_seen(path: Path, keys: Iterable[str]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "keys": sorted(set(keys))},
        ensure_ascii=False, indent=1,
    )
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def mark_new(results: list[MatchResult], seen: set[str]) -> list[bool]:
    return [pair_key(r.backlink) not in seen for r in results]
