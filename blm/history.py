"""Remember which backlink pairs earlier runs reported, so a monthly run lists only new ones.

The seen-file maps a normalised "url_from|url_to" key to the status it was
reported with ("match" or "gap") and the run ("since", e.g. "2026-10") in which
that status was first reported. A rerun with the same run id therefore
reproduces the same report, and a former content gap that now has a match is
reported again.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from blm.models import BrokenBacklink, MatchResult
from blm.verify import canonical

Seen = dict[str, dict]


class HistoryError(Exception):
    """The seen-file exists but cannot be used; message is user-facing German."""


def current_run_id() -> str:
    return datetime.now().strftime("%Y-%m")


def pair_key(bl: BrokenBacklink) -> str:
    """Scheme, www, default ports, host case and trailing slashes do not make a pair new."""
    def norm(url: Optional[str]) -> str:
        url = (url or "").strip()
        try:
            return canonical(url)
        except ValueError:
            return url
    return f"{norm(bl.url_from)}|{norm(bl.url_to)}"


def row_status(r: MatchResult) -> Optional[str]:
    if not r.top:
        return None
    return "gap" if r.is_content_gap else "match"


def load_seen(path: Path) -> Seen:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        raise HistoryError(f"Verlaufsdatei {path} ist nicht lesbar: {exc}") from exc
    keys = data.get("keys") if isinstance(data, dict) else None
    if isinstance(keys, dict) and all(
        isinstance(k, str) and isinstance(v, dict) and v.get("status") in ("match", "gap") and isinstance(v.get("since"), str)
        for k, v in keys.items()
    ):
        return {k: {"status": v["status"], "since": v["since"]} for k, v in keys.items()}
    raise HistoryError(f"Verlaufsdatei {path} hat ein unerwartetes Format.")


def save_seen(path: Path, seen: Seen) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "keys": {k: seen[k] for k in sorted(seen)}},
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


def is_new(r: MatchResult, seen: Seen, run_id: str) -> bool:
    entry = seen.get(pair_key(r.backlink))
    if entry is None:
        return True
    status = row_status(r)
    if entry["since"] == run_id and (status is None or entry["status"] == status):
        return True  # reported in this run already: a rerun shows the same rows
    return entry["status"] == "gap" and status == "match"


def mark_new(results: list[MatchResult], seen: Seen, run_id: str) -> list[bool]:
    return [is_new(r, seen, run_id) for r in results]


def record_reported(seen: Seen, reported: list[MatchResult], run_id: str) -> Seen:
    """Return a new mapping with the reported rows; existing entries only change on gap -> match."""
    out = dict(seen)
    for r in reported:
        status = row_status(r)
        if status is None:
            continue
        key = pair_key(r.backlink)
        entry = out.get(key)
        if entry is None or (entry["status"] == "gap" and status == "match"):
            out[key] = {"status": status, "since": run_id}
    return out
