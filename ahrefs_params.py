#!/usr/bin/env python
"""Print the Ahrefs MCP parameters and matching cli.py filter flags for one competitor.

Reads the "ahrefs" block of monitor.config.json, so a scheduled run never has to
assemble filters by hand. Output (JSON on stdout):
  {"mcp": {...parameters for site-explorer-broken-backlinks...},
   "cli_args": [...flags for cli.py...], "description": "..."}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from blm.ingest.ahrefs_api import AhrefsError, build_params, describe_filters

DEFAULTS = {
    "limit": 100, "min_dr": 0, "dofollow_only": True, "content_only": True, "exclude_spam": True,
    "dead_only": True, "mode": "subdomains", "aggregation": "1_per_domain", "include_traffic": False,
    "order_by": "domain_rating_source",
}
SORT_FOR_CLI = {"domain_rating_source": "domain_rating", "url_rating_source": "url_rating", "traffic": "page_traffic"}


def settings(cfg: dict) -> dict:
    block = cfg.get("ahrefs") or {}
    unknown = sorted(set(block) - set(DEFAULTS))
    if unknown:
        raise AhrefsError(f"Unbekannte Ahrefs-Einstellungen: {', '.join(unknown)}")
    return {**DEFAULTS, **block}


def build(cfg: dict, target: str) -> dict:
    s = settings(cfg)
    if not isinstance(s["limit"], int) or not 1 <= s["limit"] <= 1000:
        raise AhrefsError("ahrefs.limit muss eine ganze Zahl zwischen 1 und 1000 sein.")
    if not isinstance(s["min_dr"], (int, float)) or not 0 <= s["min_dr"] <= 100:
        raise AhrefsError("ahrefs.min_dr muss zwischen 0 und 100 liegen.")
    for key in ("dofollow_only", "content_only", "exclude_spam", "dead_only", "include_traffic"):
        if not isinstance(s[key], bool):
            raise AhrefsError(f"ahrefs.{key} muss true oder false sein.")
    mcp = build_params(target, limit=s["limit"], include_traffic=s["include_traffic"],
                       dofollow_only=s["dofollow_only"], content_only=s["content_only"],
                       exclude_spam=s["exclude_spam"], dead_only=s["dead_only"], min_dr=s["min_dr"],
                       mode=s["mode"], aggregation=s["aggregation"], order_by=s["order_by"], output="csv")
    cli_args = ["--limit", str(s["limit"]), "--min-dr", f"{s['min_dr']:g}", "--sort", SORT_FOR_CLI[s["order_by"]]]
    if not (s["dofollow_only"] and s["content_only"]):
        cli_args.append("--all-links")  # Ahrefs already filtered; cli.py must not drop the extra rows
    description = describe_filters(dofollow_only=s["dofollow_only"], content_only=s["content_only"],
                                   exclude_spam=s["exclude_spam"], dead_only=s["dead_only"], min_dr=s["min_dr"])
    return {"mcp": mcp, "cli_args": cli_args, "description": description}


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="ahrefs_params.py", description="Ahrefs-MCP-Parameter aus monitor.config.json.")
    p.add_argument("--config", type=Path, default=Path(__file__).parent / "monitor.config.json")
    p.add_argument("--target", required=True, help="Wettbewerber-Domain")
    args = p.parse_args(argv)
    try:
        cfg = json.loads(args.config.read_text(encoding="utf-8"))
        print(json.dumps(build(cfg, args.target), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        print(f"Abbruch: Konfiguration nicht lesbar: {exc}", file=sys.stderr)
        return 1
    except AhrefsError as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
