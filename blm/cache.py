"""Tiny JSON-per-entry file cache used for Wayback texts and embeddings."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Optional


class JsonCache:
    def __init__(self, root: Path = Path(".cache")):
        self.root = Path(root)

    def _path(self, namespace: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / namespace / f"{digest}.json"

    def get(self, namespace: str, key: str) -> Optional[dict]:
        path = self._path(namespace, key)
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return None
            return value
        except (ValueError, OSError):
            return None

    def set(self, namespace: str, key: str, value: dict) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, path)

    def clear(self) -> int:
        if not self.root.exists():
            return 0
        removed = 0
        for file in self.root.rglob("*.json"):
            file.unlink()
            removed += 1
        return removed
