# Agentic CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A headless pipeline module and a `cli.py` entry point so Claude Code (or a terminal user) can run the whole broken-link workflow on a Screaming Frog embeddings export and a broken-backlinks CSV without Streamlit.

**Architecture:** `blm/pipeline.py` reuses the existing modules in the same order as `app.py` (ingest → rank → wayback → embed → match → optional verify → optional drafts) and returns results plus a summary. `cli.py` parses arguments, reads keys from environment variables only, builds the provider, runs the pipeline, writes CSV/XLSX (and optional drafts Markdown), prints a summary (text or JSON). `app.py` is not touched.

**Tech Stack:** Python 3.11, argparse, existing `blm` modules, pytest + respx.

**Spec:** `docs/superpowers/specs/2026-09-30-broken-link-matcher-design.md` section 8.

## Global Constraints

- Run tests with `.venv/bin/pytest`. No network in tests (respx; injected `sleeper`).
- No Streamlit import anywhere in `blm/` or `cli.py`. `app.py` unchanged.
- API keys only from environment variables `OPENAI_API_KEY`, `GEMINI_API_KEY`; Ollama base URL from `OLLAMA_URL` (default `http://localhost:11434`). Never accept keys as CLI arguments, never print them.
- Same behavioural rules as the app: newest 200 snapshot, fallback text only from Ahrefs fields, per-backlink fallback (snapshot texts shared per dead URL, fallbacks not), sleep `pause` seconds only after an uncached Wayback fetch and not after the last URL, dimension check blocks matching, drafts only for rows with a top suggestion that are not content gaps.
- Code, comments, docstrings, commit messages English; user-facing strings German. Commit trailer as used in this repo's recent commits.

---

### Task A1: Headless pipeline module

**Files:**
- Create: `blm/pipeline.py`, `tests/test_pipeline.py`, `tests/fixtures/pipeline_frog.csv`, `tests/fixtures/pipeline_backlinks.csv`

**Interfaces:**
- Consumes: `load_frog_embeddings`, `read_table`, `detect_columns`, `parse_backlinks`, `rank_backlinks`, `recover_content(backlink, client, cache, *, max_chars, sleeper, user_agent)`, `fallback_content(backlink, error, max_chars)`, `user_agent(contact)`, `embed_cached(provider, texts, cache, *, progress)`, `build_results(ranked, recovered, vectors, own_pages, *, threshold, match_fallback)`, `verify_results(results, client, *, sleeper, pause, progress, user_agent)`, `draft_mail(row, sender, domain, *, provider, model, api_key, base_url, client, suggestion_title)`, `JsonCache`.
- Produces: `PipelineConfig`, `PipelineSummary`, `PipelineResult`, `PipelineError`, `ChatConfig`, `load_inputs(cfg) -> (FrogImport, list[BrokenBacklink])`, `run_pipeline(cfg, provider, *, chat=None, cache=None, client=None, sleeper=time.sleep, progress=None) -> PipelineResult`, `summary_to_dict(summary) -> dict`.

- [ ] **Step 1: Fixtures**

`tests/fixtures/pipeline_frog.csv`:
```
url,embedding_0,embedding_1,embedding_2
https://me.de/kueche-aus-stahl,1.0,0.0,0.0
https://me.de/holzkueche,0.0,1.0,0.0
https://me.de/glas-im-bad,0.0,0.0,1.0
```

`tests/fixtures/pipeline_backlinks.csv`:
```
url_from,url_to,anchor,snippet_left,snippet_right,title,domain_rating_source,url_rating_source,http_code_target,is_dofollow,is_content
https://blog.example/kueche,https://konkurrent.de/ratgeber/stahl,Ratgeber zu Stahlküchen,Wir empfehlen den,von Konkurrent.,Beste Küchentipps,72.,35.,404,1,1
https://forum.example/t/1,https://konkurrent.de/holz,Holzküche pflegen,,,Forum Thread,40.,10.,404,1,1
https://spam.example/x,https://konkurrent.de/nofollow,hier,,,Spam,90.,1.,404,0,1
```

- [ ] **Step 2: Failing tests**

`tests/test_pipeline.py`:
```python
import json
from pathlib import Path

import httpx
import numpy as np
import pytest
import respx

from blm.cache import JsonCache
from blm.embeddings.base import EmbeddingProvider
from blm.pipeline import (
    ChatConfig,
    PipelineConfig,
    PipelineError,
    load_inputs,
    run_pipeline,
    summary_to_dict,
)
from blm.wayback import CDX_URL, snapshot_url

FIX = Path(__file__).parent / "fixtures"
HTML = (FIX / "archived_page.html").read_text()
STAHL = "https://konkurrent.de/ratgeber/stahl"
HOLZ = "https://konkurrent.de/holz"


class KeywordProvider(EmbeddingProvider):
    """Deterministic 3-d vectors: Edelstahl/Stahl → x, Holz → y, else z."""

    name = "fake"

    def __init__(self, model="fake-3d", dimension=3):
        super().__init__(model)
        self.dimension = dimension
        self.calls: list[list[str]] = []

    def _embed_batch(self, texts):
        self.calls.append(list(texts))
        out = []
        for t in texts:
            low = t.lower()
            vec = [1.0, 0.0, 0.0] if "stahl" in low else [0.0, 1.0, 0.0] if "holz" in low else [0.0, 0.0, 1.0]
            out.append(vec[: self.dimension] + [0.0] * (self.dimension - 3))
        return out


def no_sleep(_s):
    pass


def cfg(**kw):
    base = dict(frog_path=FIX / "pipeline_frog.csv", backlinks_path=FIX / "pipeline_backlinks.csv")
    base.update(kw)
    return PipelineConfig(**base)


def mock_wayback():
    def cdx(request):
        url = request.url.params["url"]
        if url == STAHL:
            return httpx.Response(200, json=[["timestamp", "original"], ["20240315120000", STAHL]])
        return httpx.Response(200, json=[["timestamp", "original"]])

    respx.get(CDX_URL).mock(side_effect=cdx)
    respx.get(snapshot_url("20240315120000", STAHL)).mock(return_value=httpx.Response(200, html=HTML))


def test_load_inputs_reads_both_files():
    frog, backlinks = load_inputs(cfg())
    assert frog.dimension == 3 and len(frog.pages) == 3
    assert len(backlinks) == 3


def test_load_inputs_reports_missing_columns(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Quelle,Ziel\nhttps://a.de,https://b.de\n")
    with pytest.raises(PipelineError, match="Pflichtspalten"):
        load_inputs(cfg(backlinks_path=bad))


def test_dimension_mismatch_raises_before_any_fetch():
    provider = KeywordProvider(dimension=4)
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(CDX_URL).mock(return_value=httpx.Response(200, json=[]))
        with pytest.raises(PipelineError, match="Dimension"):
            run_pipeline(cfg(), provider, sleeper=no_sleep)
        assert route.call_count == 0


@respx.mock
def test_full_run_matches_and_counts(tmp_path):
    mock_wayback()
    provider = KeywordProvider()
    sleeps: list[float] = []
    stages: list[tuple[str, int, int]] = []
    res = run_pipeline(cfg(), provider, cache=JsonCache(tmp_path), sleeper=sleeps.append,
                       progress=lambda s, d, t: stages.append((s, d, t)))
    s = res.summary
    assert s.backlinks_total == 3 and s.backlinks_ranked == 2  # nofollow row filtered
    assert s.snapshots == 1 and s.fallbacks == 1 and s.no_text == 0
    assert s.matched == 2 and s.content_gaps == 0 and s.unmatched == 0
    assert s.own_pages == 3 and s.dimension == 3
    assert [r.top[0].url for r in res.results] == ["https://me.de/kueche-aus-stahl", "https://me.de/holzkueche"]
    assert res.results[0].priority == 1
    assert sleeps == [1.0]  # pause after the one uncached fetch; the fallback row made no fetch
    assert any(st[0] == "wayback" for st in stages) and any(st[0] == "embedding" for st in stages)
    assert s.verified == {} and s.drafts == 0


@respx.mock
def test_second_run_uses_cache_and_does_not_sleep(tmp_path):
    mock_wayback()
    cache = JsonCache(tmp_path)
    run_pipeline(cfg(), KeywordProvider(), cache=cache, sleeper=no_sleep)
    sleeps: list[float] = []
    provider = KeywordProvider()
    run_pipeline(cfg(), provider, cache=cache, sleeper=sleeps.append)
    assert sleeps == []
    assert provider.calls == [] or all("stahl" not in t.lower() for batch in provider.calls for t in batch) is False or True


@respx.mock
def test_threshold_marks_content_gap(tmp_path):
    mock_wayback()
    res = run_pipeline(cfg(threshold=1.01), KeywordProvider(), cache=JsonCache(tmp_path), sleeper=no_sleep)
    assert res.summary.content_gaps == 2 and res.summary.matched == 0


@respx.mock
def test_verify_flag_runs_live_check(tmp_path):
    mock_wayback()
    respx.get(STAHL).mock(return_value=httpx.Response(404))
    respx.get(HOLZ).mock(return_value=httpx.Response(200, text="alive"))
    respx.get("https://blog.example/kueche").mock(return_value=httpx.Response(200, html=f'<a href="{STAHL}">x</a>'))
    res = run_pipeline(cfg(verify=True), KeywordProvider(), cache=JsonCache(tmp_path), sleeper=no_sleep)
    assert res.summary.verified == {"confirmed": 1, "fixed": 1}
    assert [r.verification for r in res.results] == ["confirmed", "fixed"]


@respx.mock
def test_drafts_flag_produces_mail_per_matched_row(tmp_path):
    mock_wayback()
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Hallo Entwurf"}}]}))
    chat = ChatConfig(provider="openai", model="gpt-4.1-mini", api_key="k")
    res = run_pipeline(cfg(drafts=True, sender_name="Daniel", own_domain="me.de"), KeywordProvider(),
                       chat=chat, cache=JsonCache(tmp_path), sleeper=no_sleep)
    assert res.summary.drafts == 2
    assert set(res.drafts) == {"https://blog.example/kueche|" + STAHL, "https://forum.example/t/1|" + HOLZ}
    assert all(v == "Hallo Entwurf" for v in res.drafts.values())


def test_drafts_require_sender_and_domain():
    with pytest.raises(PipelineError, match="Absender"):
        run_pipeline(cfg(drafts=True), KeywordProvider(), chat=ChatConfig("openai", "m", "k"), sleeper=no_sleep)


@respx.mock
def test_draft_error_is_recorded_not_raised(tmp_path):
    mock_wayback()
    respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(500, text="boom"))
    res = run_pipeline(cfg(drafts=True, sender_name="D", own_domain="me.de"), KeywordProvider(),
                       chat=ChatConfig("openai", "m", "k"), cache=JsonCache(tmp_path), sleeper=no_sleep)
    assert res.summary.drafts == 0
    assert len(res.summary.errors) == 2 and all("Mail-Entwurf" in e for e in res.summary.errors)


def test_summary_to_dict_is_json_serialisable(tmp_path):
    with respx.mock:
        mock_wayback()
        res = run_pipeline(cfg(), KeywordProvider(), cache=JsonCache(tmp_path), sleeper=no_sleep)
    text = json.dumps(summary_to_dict(res.summary), ensure_ascii=False)
    assert '"matched": 2' in text
```

Note on `test_second_run_uses_cache_and_does_not_sleep`: the last assertion line is deliberately a no-op placeholder in this plan text; replace it with `assert sleeps == []` only (delete the provider.calls line). The embedding cache is keyed by provider name and model, so the second run also makes no embedding calls: add `assert provider.calls == []` as the real second assertion.

- [ ] **Step 3: Run tests to see them fail**

Run: `.venv/bin/pytest tests/test_pipeline.py -q` → ImportError on `blm.pipeline`.

- [ ] **Step 4: Implement**

`blm/pipeline.py`:
```python
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
from blm.ranking import rank_backlinks
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
    errors: list[str] = field(default_factory=list)


@dataclass
class PipelineResult:
    results: list[MatchResult]
    summary: PipelineSummary
    drafts: dict[str, str] = field(default_factory=dict)  # "url_from|url_to" -> mail text


def summary_to_dict(summary: PipelineSummary) -> dict:
    return asdict(summary)


def load_inputs(cfg: PipelineConfig) -> tuple[FrogImport, list[BrokenBacklink]]:
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
    return frog, parse_backlinks(df, cm.mapping)


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

    frog, backlinks = load_inputs(cfg)
    summary = PipelineSummary(own_pages=len(frog.pages), backlinks_total=len(backlinks))
    summary.dimension = _check_dimension(provider, frog)

    ranked = rank_backlinks(
        backlinks, dofollow_only=cfg.dofollow_only, content_only=cfg.content_only,
        min_dr=cfg.min_dr, sort_by=cfg.sort_by, limit=cfg.limit,
    )
    summary.backlinks_ranked = len(ranked)
    agent = user_agent(cfg.contact)

    own_client = client is None
    client = client or httpx.Client()
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
            for n, r in enumerate(candidates, start=1):
                key = f"{r.backlink.url_from}|{r.backlink.url_to}"
                try:
                    drafts[key] = draft_mail(
                        r, cfg.sender_name.strip(), cfg.own_domain.strip(),
                        provider=chat.provider, model=chat.model, api_key=chat.api_key,
                        base_url=chat.base_url, client=client, suggestion_title=titles.get(r.top[0].url, ""),
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
```

- [ ] **Step 5: Run tests, then the full suite**

Run: `.venv/bin/pytest tests/test_pipeline.py -v` → all pass. Then `.venv/bin/pytest -q`.

- [ ] **Step 6: Commit**

`feat: headless pipeline module for CLI and agent use`

---

### Task A2: cli.py, docs and README

**Files:**
- Create: `cli.py`, `tests/test_cli.py`, `docs/agentic-workflow.md`
- Modify: `README.md` (new section "Agentischer Weg (Claude Code / Terminal)" before "Tests")

**Interfaces:**
- Consumes: `blm.pipeline` (Task A1), `make_provider`, `PROVIDERS`, `DEFAULT_EMBED_MODELS`, `DEFAULT_CHAT_MODELS`, `SORT_FIELDS`, `results_to_dataframe`, `to_csv_bytes`, `to_xlsx_bytes`, `JsonCache`.
- Produces: `cli.main(argv: list[str] | None = None) -> int`, `cli.build_parser()`, `cli.write_output(result, out_path, drafts_path)`, `cli.summary_lines(summary) -> list[str]`.

- [ ] **Step 1: Failing tests**

`tests/test_cli.py`:
```python
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx

import cli
from blm.wayback import CDX_URL, snapshot_url
from tests.test_pipeline import HTML, STAHL, KeywordProvider

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def fake_provider(monkeypatch):
    prov = KeywordProvider()
    monkeypatch.setattr(cli, "make_provider", lambda *a, **k: prov)
    monkeypatch.setattr(cli, "default_sleeper", lambda s: None)
    return prov


def mock_wayback():
    def cdx(request):
        if request.url.params["url"] == STAHL:
            return httpx.Response(200, json=[["timestamp", "original"], ["20240315120000", STAHL]])
        return httpx.Response(200, json=[["timestamp", "original"]])
    respx.get(CDX_URL).mock(side_effect=cdx)
    respx.get(snapshot_url("20240315120000", STAHL)).mock(return_value=httpx.Response(200, html=HTML))


def base_args(tmp_path, out="ergebnis.xlsx"):
    return ["--frog", str(FIX / "pipeline_frog.csv"), "--backlinks", str(FIX / "pipeline_backlinks.csv"),
            "--provider", "openai", "--model", "text-embedding-3-small", "--out", str(tmp_path / out),
            "--cache-dir", str(tmp_path / "cache")]


def test_missing_key_exits_1_with_hint(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert cli.main(base_args(tmp_path)) == 1
    assert "OPENAI_API_KEY" in capsys.readouterr().err


@respx.mock
def test_run_writes_xlsx_and_prints_summary(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    assert cli.main(base_args(tmp_path)) == 0
    df = pd.read_excel(tmp_path / "ergebnis.xlsx")
    assert len(df) == 2 and df.loc[0, "Vorschlag 1"] == "https://me.de/kueche-aus-stahl"
    out = capsys.readouterr()
    assert "Treffer" in out.out and "2" in out.out


@respx.mock
def test_json_output_is_machine_readable(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    assert cli.main(base_args(tmp_path, out="e.csv") + ["--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["matched"] == 2 and data["output"].endswith("e.csv")
    assert (tmp_path / "e.csv").read_bytes().startswith("﻿".encode())


@respx.mock
def test_drafts_written_as_markdown(monkeypatch, tmp_path, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    mock_wayback()
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Hallo Entwurf"}}]}))
    args = base_args(tmp_path) + ["--drafts", "--sender", "Daniel", "--domain", "me.de",
                                  "--drafts-out", str(tmp_path / "drafts.md")]
    assert cli.main(args) == 0
    md = (tmp_path / "drafts.md").read_text()
    assert md.count("Hallo Entwurf") == 2 and "https://blog.example/kueche" in md


def test_drafts_without_sender_exit_1(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert cli.main(base_args(tmp_path) + ["--drafts"]) == 1
    assert "sender" in capsys.readouterr().err.lower()


def test_unknown_file_exits_1(monkeypatch, tmp_path, capsys, fake_provider):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    args = base_args(tmp_path)
    args[args.index("--frog") + 1] = str(tmp_path / "nope.csv")
    assert cli.main(args) == 1
    assert "Frog" in capsys.readouterr().err


def test_bad_out_extension_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(base_args(tmp_path, out="e.txt"))
    assert exc.value.code == 2


def test_ollama_needs_no_key(monkeypatch, tmp_path, fake_provider):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_URL", raising=False)
    with respx.mock:
        mock_wayback()
        args = base_args(tmp_path)
        args[args.index("--provider") + 1] = "ollama"
        assert cli.main(args) == 0


def test_key_never_appears_in_help_or_errors(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    assert "api-key" not in capsys.readouterr().out.lower()
```

- [ ] **Step 2: Implement `cli.py`**

```python
#!/usr/bin/env python
"""Broken Link Matcher on the command line.

Runs the same workflow as the Streamlit app without a browser, so Claude Code
or a shell script can drive it. Keys come from environment variables only:
OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL (default http://localhost:11434).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

from blm.cache import JsonCache
from blm.embeddings import DEFAULT_EMBED_MODELS, PROVIDERS, EmbeddingError, make_provider
from blm.export import results_to_dataframe, to_csv_bytes, to_xlsx_bytes
from blm.outreach import DEFAULT_CHAT_MODELS
from blm.pipeline import ChatConfig, PipelineConfig, PipelineError, PipelineResult, run_pipeline, summary_to_dict
from blm.ranking import SORT_FIELDS

default_sleeper = time.sleep
ENV_KEYS = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cli.py",
        description="Broken Link Matcher: tote Wettbewerber-URLs mit eigenen Seiten matchen (ohne Oberfläche).",
        epilog="Schlüssel nur über Umgebungsvariablen: OPENAI_API_KEY, GEMINI_API_KEY, OLLAMA_URL.",
    )
    p.add_argument("--frog", required=True, type=Path, help="Screaming-Frog-Embeddings-Export (CSV)")
    p.add_argument("--backlinks", required=True, type=Path, help="Broken-Backlinks-Export (CSV/XLSX)")
    p.add_argument("--provider", choices=PROVIDERS, default="openai", help="Embedding-Anbieter wie im Frog")
    p.add_argument("--model", help="Embedding-Modell wie im Frog (Standard je Anbieter)")
    p.add_argument("--out", required=True, type=Path, help="Ergebnisdatei .xlsx oder .csv")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--min-dr", type=float, default=0.0)
    p.add_argument("--sort", choices=SORT_FIELDS, default="domain_rating")
    p.add_argument("--all-links", action="store_true", help="auch Nofollow- und Nicht-Content-Links")
    p.add_argument("--threshold", type=float, default=0.5, help="Content-Gap unterhalb dieses Scores")
    p.add_argument("--no-fallback", action="store_true", help="Zeilen ohne Snapshot nicht matchen")
    p.add_argument("--max-chars", type=int, default=12000)
    p.add_argument("--pause", type=float, default=1.0, help="Sekunden Pause nach jedem Wayback-Abruf")
    p.add_argument("--contact", help="Kontakt (Mail oder URL) für den User-Agent")
    p.add_argument("--verify", action="store_true", help="Live prüfen: Ziel noch 404, Link noch vorhanden")
    p.add_argument("--drafts", action="store_true", help="Mail-Entwürfe erzeugen (braucht --sender und --domain)")
    p.add_argument("--sender", default="", help="Absender-Name für Mail-Entwürfe")
    p.add_argument("--domain", default="", help="eigene Domain für Mail-Entwürfe")
    p.add_argument("--chat-model", help="Chat-Modell für Entwürfe (Standard je Anbieter)")
    p.add_argument("--drafts-out", type=Path, help="Markdown-Datei für die Mail-Entwürfe")
    p.add_argument("--cache-dir", type=Path, default=Path(__file__).parent / ".cache")
    p.add_argument("--json", action="store_true", help="Zusammenfassung als JSON auf stdout")
    p.add_argument("--quiet", action="store_true", help="keinen Fortschritt auf stderr")
    return p


def resolve_credentials(provider: str) -> tuple[Optional[str], Optional[str]]:
    """(api_key, base_url) from the environment; raises PipelineError with the variable name."""
    if provider == "ollama":
        return None, os.environ.get("OLLAMA_URL") or "http://localhost:11434"
    var = ENV_KEYS[provider]
    key = os.environ.get(var, "").strip()
    if not key:
        raise PipelineError(f"Umgebungsvariable {var} ist nicht gesetzt.")
    return key, None


def write_output(result: PipelineResult, out_path: Path, drafts_path: Optional[Path]) -> None:
    df = results_to_dataframe(result.results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".xlsx":
        out_path.write_bytes(to_xlsx_bytes(df))
    else:
        out_path.write_bytes(to_csv_bytes(df))
    if drafts_path is not None:
        lines = ["# Mail-Entwürfe", ""]
        for key, text in result.drafts.items():
            url_from, url_to = key.split("|", 1)
            lines += [f"## {url_from}", "", f"Tote URL: {url_to}", "", text, ""]
        drafts_path.parent.mkdir(parents=True, exist_ok=True)
        drafts_path.write_text("\n".join(lines), encoding="utf-8")


def summary_lines(summary) -> list[str]:
    s = summary
    lines = [
        f"Eigene Seiten: {s.own_pages} (Dimension {s.dimension})",
        f"Backlinks: {s.backlinks_total} geladen, {s.backlinks_ranked} nach Filter",
        f"Wayback: {s.snapshots} Snapshots, {s.fallbacks} Fallbacks, {s.no_text} ohne Text",
        f"Treffer: {s.matched}, Content-Gaps: {s.content_gaps}, nicht gematcht: {s.unmatched}",
    ]
    if s.verified:
        lines.append("Verifikation: " + ", ".join(f"{k} {v}" for k, v in sorted(s.verified.items())))
    if s.drafts:
        lines.append(f"Mail-Entwürfe: {s.drafts}")
    for e in s.errors:
        lines.append(f"Fehler: {e}")
    return lines


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.out.suffix.lower() not in (".xlsx", ".csv"):
        parser.error("--out muss auf .xlsx oder .csv enden")
    if args.drafts and (not args.sender.strip() or not args.domain.strip()):
        print("Mail-Entwürfe brauchen --sender und --domain.", file=sys.stderr)
        return 1

    def progress(stage: str, done: int, total: int) -> None:
        if not args.quiet:
            print(f"[{stage}] {done}/{total}", file=sys.stderr, end="\r" if done < total else "\n")

    try:
        api_key, base_url = resolve_credentials(args.provider)
        model = args.model or DEFAULT_EMBED_MODELS[args.provider]
        provider = make_provider(args.provider, model, api_key=api_key, base_url=base_url)
        chat = ChatConfig(args.provider, args.chat_model or DEFAULT_CHAT_MODELS[args.provider], api_key, base_url) if args.drafts else None
        cfg = PipelineConfig(
            frog_path=args.frog, backlinks_path=args.backlinks,
            dofollow_only=not args.all_links, content_only=not args.all_links,
            min_dr=args.min_dr, sort_by=args.sort, limit=args.limit, max_chars=args.max_chars,
            threshold=args.threshold, match_fallback=not args.no_fallback,
            verify=args.verify, drafts=args.drafts, sender_name=args.sender, own_domain=args.domain,
            contact=args.contact, pause=args.pause,
        )
        result = run_pipeline(cfg, provider, chat=chat, cache=JsonCache(args.cache_dir),
                              sleeper=default_sleeper, progress=progress)
        write_output(result, args.out, args.drafts_out if args.drafts else None)
    except (PipelineError, EmbeddingError) as exc:
        print(f"Abbruch: {exc}", file=sys.stderr)
        return 1

    if args.json:
        payload = summary_to_dict(result.summary)
        payload["output"] = str(args.out)
        if args.drafts_out and args.drafts:
            payload["drafts_output"] = str(args.drafts_out)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in summary_lines(result.summary):
            print(line)
        print(f"Ergebnis: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Write `docs/agentic-workflow.md`**

Content (German): purpose (same workflow, no UI, Claude Code as orchestrator); prerequisites (Claude Code in the repo folder, Screaming Frog MCP and Ahrefs MCP connected, Frog configuration file with embeddings enabled saved once in the Frog UI, venv installed, `OPENAI_API_KEY` or alternative exported in the shell that starts Claude Code); the three-step prompt:

```
Führe den Broken-Link-Workflow für meine Domain meine-domain.de gegen den Wettbewerber konkurrent.de aus:

1. Screaming Frog MCP: lade den letzten Crawl von meine-domain.de (oder starte einen Crawl mit der Konfiguration /Pfad/zu/embeddings.seospiderconfig) und exportiere die Embeddings als CSV nach frog-embeddings.csv.
2. Ahrefs MCP: hol die Broken Backlinks von konkurrent.de (mode subdomains, aggregation 1_per_domain, nur is_dofollow=true und is_content=true, sortiert nach domain_rating_source absteigend, limit 100, output csv, select url_from,url_to,anchor,snippet_left,snippet_right,title,domain_rating_source,url_rating_source,http_code_target,is_dofollow,is_content) und speichere sie als broken-backlinks-konkurrent.csv.
3. Führe aus: .venv/bin/python cli.py --frog <Pfad aus Schritt 1> --backlinks broken-backlinks-konkurrent.csv --provider openai --model text-embedding-3-small --out ergebnis.xlsx --verify --json
4. Lies die JSON-Zusammenfassung und die ersten Zeilen der Excel-Datei und sag mir, welche fünf Linkgeber ich zuerst anschreiben sollte und warum. Content-Gaps bitte separat auflisten.
```

Plus: where the Frog MCP writes files (its allowed directory, printed by the MCP), that the CLI accepts absolute paths; the full CLI reference (`python cli.py --help` output pasted); exit codes; a note that keys never go on the command line; and a "Mit Mail-Entwürfen" variant adding `--drafts --sender "Name" --domain meine-domain.de --drafts-out entwuerfe.md`.

- [ ] **Step 4: README section**

Add before "## Tests": `## Agentischer Weg (Claude Code / Terminal)` with 6 to 8 lines: what cli.py does, one example call, keys via environment, link to `docs/agentic-workflow.md`, note that app and CLI share the `.cache/` folder.

- [ ] **Step 5: Run tests and help**

Run: `.venv/bin/pytest -q`; `.venv/bin/python cli.py --help` prints without error.

- [ ] **Step 6: Commit**

`feat: command-line entry point and agentic workflow docs`
