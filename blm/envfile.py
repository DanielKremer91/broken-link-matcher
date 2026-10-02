"""Read KEY=value lines from a local .env file into os.environ without overriding the shell."""

from __future__ import annotations

import os
import re
from pathlib import Path

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env_file(path: Path) -> list[str]:
    """Set variables that are not already set; returns the names that were set (never values)."""
    path = Path(path)
    if not path.is_file():
        return []
    applied = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _LINE.match(line)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if not value or os.environ.get(name):
            continue
        os.environ[name] = value
        applied.append(name)
    return applied
