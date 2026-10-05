#!/usr/bin/env python
"""Check an early sample of a Screaming Frog export: do HTML pages already carry embeddings?

Used by the monthly monitor shortly after the crawl starts, so a missing
JavaScript rendering or a broken snippet is caught after minutes, not hours.
Prints JSON: {"html_rows", "with_vectors", "dimension", "verdict"} where verdict is
"ok", "keine_embeddings" or "zu_wenig_daten".
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import pandas as pd

from blm.ingest.frog_csv import MIN_CONTENT_DIMENSION, _parse_vector, detect_frog_columns
from blm.ingest.tables import read_table
from frog_crawl_check import MIN_DOMAIN_SHARE, _on_domain


def probe(path: Path, field: Optional[str] = None, min_html: int = 10, domain: Optional[str] = None) -> dict:
    df = read_table(path)
    columns = {c.strip().lower(): c for c in df.columns}
    detected = detect_frog_columns(df)
    vector_col = field if field in df.columns else detected.vector_col
    ctype = columns.get("content type")
    status = columns.get("status code")
    rows = df
    if ctype:
        rows = rows[rows[ctype].astype(str).str.contains("html", case=False, na=False)]
    if status:
        rows = rows[rows[status].astype(str).str.strip().isin(["200", "200.0"])]
    sizes: Counter = Counter()
    if not vector_col and detected.wide_cols:
        # export of Frog's built-in AI embeddings: one number per column embedding_0 ... embedding_N
        numeric = rows[detected.wide_cols].apply(lambda col: pd.to_numeric(col.astype(str).str.replace(",", "."), errors="coerce"))
        filled = int(numeric.notna().all(axis=1).sum())
        if filled:
            sizes[len(detected.wide_cols)] = filled
    elif vector_col:
        for raw in rows[vector_col].tolist():
            vec = _parse_vector(raw)
            if vec is not None and vec.size >= MIN_CONTENT_DIMENSION:
                sizes[vec.size] += 1
    with_vectors = sum(sizes.values())
    if with_vectors:
        verdict = "ok"
    elif len(rows) >= min_html:
        verdict = "keine_embeddings"
    else:
        verdict = "zu_wenig_daten"
    result = {"html_rows": int(len(rows)), "with_vectors": int(with_vectors),
              "dimension": int(sizes.most_common(1)[0][0]) if sizes else 0, "verdict": verdict}
    addr_col = columns.get("address") or columns.get("url")
    if domain and addr_col and len(df):
        on = sum(_on_domain(a, domain) for a in df[addr_col].tolist())
        result["on_domain_share"] = round(on / len(df), 3)
        if result["on_domain_share"] < MIN_DOMAIN_SHARE:
            result["verdict"] = "falsche_domain"  # the loaded crawl is not this customer's site
    return result


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="frog_probe.py", description="Stichprobe eines Frog-Exports auf Embeddings prüfen.")
    p.add_argument("export", type=Path, help="NDJSON- oder CSV-Export aus Screaming Frog")
    p.add_argument("--field", help="Name der Embedding-Spalte, z. B. 'Embeddings Fressnapf 1'")
    p.add_argument("--min-html", type=int, default=10, help="so viele HTML-Seiten braucht ein Urteil")
    p.add_argument("--domain", help="eigene Domain: prüft, ob der Export wirklich diese Website ist")
    args = p.parse_args(argv)
    try:
        result = probe(args.export, args.field, args.min_html, args.domain)
    except (OSError, ValueError) as exc:
        print(f"Abbruch: Export nicht lesbar: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
