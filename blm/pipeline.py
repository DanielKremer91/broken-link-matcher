"""Headless pipeline: the same steps as app.py, without Streamlit state.

Used by cli.py and by anyone driving the workflow from Python (for example
Claude Code after fetching the inputs through the Screaming Frog and Ahrefs
MCP servers).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Optional

import httpx

from blm.cache import JsonCache
from blm.embeddings import embed_cached
from blm.embeddings.base import EmbeddingError, EmbeddingProvider
from blm.ingest.backlinks_csv import detect_columns, parse_backlinks, read_table
from blm.ingest.frog_csv import FrogImport, load_frog_embeddings
from blm.matcher import build_results
from blm.models import BrokenBacklink, MatchResult, RecoveredContent
from blm.outreach import OutreachError, draft_mail
from blm.ranking import SORT_FIELDS, rank_backlinks
from blm.verify import verify_results
from blm.wayback import fallback_content, recover_content, user_agent

ProgressFn = Callable[[str, int, int], None]  # (stage, done, total)


class PipelineError(Exception):
    """Configuration or input problem that stops the run; message is user-facing German."""


@dataclass
class PipelineConfig:
    frog_path: Path
    backlinks_path: Path
    dofollow_only: bool = True
    content_only: bool = True
    min_dr: float = 0.0
    sort_by: str = "domain_rating"
    limit: int = 100
    max_chars: int = 12000
    threshold: float = 0.5
    match_fallback: bool = True
    verify: bool = False
    drafts: bool = False
    sender_name: str = ""
    own_domain: str = ""
    contact: Optional[str] = None
    pause: float = 1.0


@dataclass
class ChatConfig:
    provider: str
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None


@dataclass
class PipelineSummary:
    own_pages: int = 0
    dimension: int = 0
    backlinks_total: int = 0
    backlinks_ranked: int = 0
    snapshots: int = 0
    fallbacks: int = 0
    no_text: int = 0
    matched: int = 0
    content_gaps: int = 0
    unmatched: int = 0
    verified: dict[str, int] = field(default_factory=dict)
    drafts: int = 0
    excel_dates_repaired: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    results: list[MatchResult]
    summary: PipelineSummary
    drafts: dict[str, str] = field(default_factory=dict)  # "url_from|url_to" -> mail text


def summary_to_dict(summary: PipelineSummary) -> dict:
    return asdict(summary)


def load_inputs(cfg: PipelineConfig, *, report: Optional[dict] = None) -> tuple[FrogImport, list[BrokenBacklink]]:
    """Read both inputs (CSV/TSV/TXT or Excel). `report` receives parse_backlinks' counters."""
    try:
        frog = load_frog_embeddings(cfg.frog_path)
    except (ValueError, OSError) as exc:
        raise PipelineError(f"Frog-Export konnte nicht gelesen werden: {exc}") from exc
    try:
        df = read_table(cfg.backlinks_path)
    except (ValueError, OSError) as exc:
        raise PipelineError(f"Backlink-Datei konnte nicht gelesen werden: {exc}") from exc
    cm = detect_columns(df)
    if cm.missing:
        raise PipelineError(
            f"Pflichtspalten nicht erkannt: {', '.join(cm.missing)}. Gefundene Spalten: {', '.join(cm.columns)}"
        )
    return frog, parse_backlinks(df, cm.mapping, report=report)


def _check_dimension(provider: EmbeddingProvider, frog: FrogImport) -> int:
    try:
        dim = provider.probe_dimension()
    except EmbeddingError as exc:
        raise PipelineError(f"Embedding-Anbieter nicht erreichbar: {exc}") from exc
    if dim != frog.dimension:
        raise PipelineError(
            f"Dimension passt nicht: Frog-Export {frog.dimension}, Modell {dim}. Wähle exakt das im Frog konfigurierte Modell."
        )
    return dim


def _recover_all(
    ranked: list[BrokenBacklink],
    client: httpx.Client,
    cache: Optional[JsonCache],
    *,
    max_chars: int,
    agent: str,
    sleeper: Callable[[float], None],
    pause: float,
    progress: Optional[ProgressFn],
) -> list[RecoveredContent]:
    """Same rules as the app: snapshot texts are shared per dead URL, fallbacks are per backlink."""
    snapshots: dict[str, RecoveredContent] = {}
    failed: dict[str, Optional[str]] = {}
    out: list[RecoveredContent] = []
    for i, bl in enumerate(ranked, start=1):
        if bl.url_to in snapshots:
            rc = snapshots[bl.url_to]
        elif bl.url_to in failed:
            rc = fallback_content(bl, failed[bl.url_to], max_chars)
        else:
            cached = cache is not None and cache.get("wayback", bl.url_to) is not None
            rc = recover_content(bl, client, cache, max_chars=max_chars, sleeper=sleeper, user_agent=agent)
            if rc.source == "wayback":
                snapshots[bl.url_to] = rc
            else:
                failed[bl.url_to] = rc.error
            if not cached and i < len(ranked):
                sleeper(pause)
        out.append(rc)
        if progress:
            progress("wayback", i, len(ranked))
    return out


def run_pipeline(
    cfg: PipelineConfig,
    provider: EmbeddingProvider,
    *,
    chat: Optional[ChatConfig] = None,
    cache: Optional[JsonCache] = None,
    client: Optional[httpx.Client] = None,
    sleeper: Callable[[float], None] = time.sleep,
    progress: Optional[ProgressFn] = None,
) -> PipelineResult:
    if cfg.drafts and (not cfg.sender_name.strip() or not cfg.own_domain.strip()):
        raise PipelineError("Mail-Entwürfe brauchen Absender-Name und eigene Domain.")
    if cfg.drafts and chat is None:
        raise PipelineError("Mail-Entwürfe brauchen eine Chat-Konfiguration (Anbieter und Modell).")

    if (cfg.drafts and chat is not None and chat.provider in ("openai", "gemini")
            and not (chat.api_key or "").strip()):
        raise PipelineError("API-Schlüssel für Mail-Entwürfe fehlt.")
    if cfg.sort_by not in SORT_FIELDS:
        raise PipelineError(f"Unbekanntes Sortierkriterium: {cfg.sort_by}. Erlaubt: {', '.join(SORT_FIELDS)}")

    report: dict = {}
    frog, backlinks = load_inputs(cfg, report=report)
    summary = PipelineSummary(own_pages=len(frog.pages), backlinks_total=len(backlinks),
                              excel_dates_repaired=report.get("excel_dates_repaired", 0))
    summary.dimension = _check_dimension(provider, frog)

    ranked = rank_backlinks(
        backlinks, dofollow_only=cfg.dofollow_only, content_only=cfg.content_only,
        min_dr=cfg.min_dr, sort_by=cfg.sort_by, limit=cfg.limit,
    )
    summary.backlinks_ranked = len(ranked)
    agent = user_agent(cfg.contact)

    own_client = client is None
    client = client or httpx.Client(timeout=httpx.Timeout(30.0))
    try:
        recovered = _recover_all(ranked, client, cache, max_chars=cfg.max_chars, agent=agent,
                                 sleeper=sleeper, pause=cfg.pause, progress=progress)
        for rc in recovered:
            if rc.source == "wayback":
                summary.snapshots += 1
            elif rc.source == "fallback":
                summary.fallbacks += 1
            else:
                summary.no_text += 1

        texts = [rc.text for rc in recovered]
        idx = [i for i, t in enumerate(texts) if t]
        try:
            fresh = embed_cached(provider, [texts[i] for i in idx], cache,
                                 progress=(lambda d, t: progress("embedding", d, t)) if progress else None)
        except EmbeddingError as exc:
            raise PipelineError(f"Embedding fehlgeschlagen: {exc}") from exc
        vectors: list = [None] * len(texts)
        for j, i in enumerate(idx):
            vectors[i] = fresh[j]

        results = build_results(ranked, recovered, vectors, frog.pages,
                                threshold=cfg.threshold, match_fallback=cfg.match_fallback)
        for r in results:
            if r.is_content_gap:
                summary.content_gaps += 1
            elif r.top:
                summary.matched += 1
            else:
                summary.unmatched += 1

        if cfg.verify:
            verify_results(results, client, sleeper=sleeper,
                           progress=(lambda d, t: progress("verify", d, t)) if progress else None,
                           user_agent=agent)
            for r in results:
                summary.verified[r.verification] = summary.verified.get(r.verification, 0) + 1

        drafts: dict[str, str] = {}
        if cfg.drafts and chat is not None:
            titles = {p.url: p.title for p in frog.pages}
            candidates = [r for r in results if r.top and not r.is_content_gap]
            seen: dict[str, int] = {}
            for n, r in enumerate(candidates, start=1):
                base = f"{r.backlink.url_from}|{r.backlink.url_to}"
                seen[base] = seen.get(base, 0) + 1
                key = base if seen[base] == 1 else f"{base}#{seen[base]}"  # same page may link the dead URL twice
                try:
                    drafts[key] = draft_mail(
                        r, cfg.sender_name.strip(), cfg.own_domain.strip(),
                        provider=chat.provider, model=chat.model, api_key=chat.api_key,
                        base_url=chat.base_url, client=None, suggestion_title=titles.get(r.top[0].url, ""),
                    )
                except OutreachError as exc:
                    msg = f"Mail-Entwurf fehlgeschlagen für {r.backlink.url_from}: {exc}"
                    r.errors.append(msg)
                    summary.errors.append(msg)
                if progress:
                    progress("drafts", n, len(candidates))
            summary.drafts = len(drafts)
    finally:
        if own_client:
            client.close()

    return PipelineResult(results=results, summary=summary, drafts=drafts)
