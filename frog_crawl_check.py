#!/usr/bin/env python
"""Check how complete a Screaming Frog crawl is, from an "Internal: All" export.

URLs with status code 0 got no response at all (connection lost, rendering
timeout). Prints JSON: {"internal", "no_response", "share", "reasons", "verdict"}
with verdict "ok" (under 5 percent), "warnung" (5 to 30 percent) or
"unvollstaendig" (over 30 percent).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

from blm.ingest.tables import read_table

WARN_SHARE = 0.05
FAIL_SHARE = 0.30


def crawl_health(path: Path) -> dict:
    df = read_table(path)
    cols = {c.strip().lower(): c for c in df.columns}
    code_col = cols.get("status code")
    if code_col is None:
        raise ValueError("Spalte 'Status Code' fehlt im Export")
    status_col = cols.get("status")
    codes = df[code_col].astype(str).str.strip()
    no_resp = df[codes.isin(["0", "0.0", ""])]
    reasons = Counter(no_resp[status_col].astype(str).str.strip().replace("", "unbekannt")) if status_col else Counter()
    total = len(df)
    share = len(no_resp) / total if total else 0.0
    verdict = "ok" if share < WARN_SHARE else ("warnung" if share < FAIL_SHARE else "unvollstaendig")
    return {"internal": total, "no_response": int(len(no_resp)), "share": round(share, 3),
            "reasons": dict(reasons.most_common(5)), "verdict": verdict}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="frog_crawl_check.py", description="Vollständigkeit eines Frog-Crawls prüfen.")
    p.add_argument("export", type=Path, help="Export 'Internal: All' mit Status Code und Status (NDJSON oder CSV)")
    args = p.parse_args(argv)
    try:
        result = crawl_health(args.export)
    except (OSError, ValueError) as exc:
        print(f"Abbruch: Export nicht lesbar: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
