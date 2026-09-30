# Broken Link Matcher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Streamlit tool that takes a competitor's broken backlinks, recovers the dead pages' content from the Wayback Machine, embeds it, and finds the three most similar pages of the user's own domain (embedded by Screaming Frog), then drafts an outreach mail per hit.

**Architecture:** Pure-Python package `blm` with one module per pipeline step (ingest, ranking, wayback, embeddings, matcher, verify, outreach, cache, export) and a thin Streamlit `app.py` that only wires them together. No module in `blm` imports Streamlit. All HTTP goes through `httpx` so tests mock it with `respx`.

**Tech Stack:** Python 3.11 via `uv`, Streamlit, httpx, pandas, numpy, trafilatura, beautifulsoup4, openpyxl, pytest, respx.

**Spec:** `docs/superpowers/specs/2026-09-30-broken-link-matcher-design.md`

## Global Constraints

- Python 3.11 or newer. Only Python 3.9 is installed system-wide; use `uv` (`uv python install 3.11`, `uv venv --python 3.11 .venv`). Run every command below with the venv activated or via `.venv/bin/<cmd>`.
- No provider SDKs. OpenAI, Gemini and Ollama are called over HTTP with `httpx`.
- No network access in tests. Mock HTTP with `respx`.
- UI copy is German. Code, comments, commit messages and docstrings are English.
- Fallback text is a plain concatenation of existing Ahrefs fields (title_from, anchor, snippet_left, snippet_right, URL path words). Never generated, never LLM-produced. If all those fields are empty the text is `None` and the row is not matched.
- Wayback: always the newest snapshot with status 200 (`limit=-1` on the CDX API). Fetch raw HTML with the `id_` flag. 1 second between requests, retries on 429/5xx with 2, 4, 8 second pauses.
- Default limit 100 backlinks per competitor. Default similarity threshold 0.5. Default text cap 12000 characters.
- Secrets live only in Streamlit session state, environment variables or `st.secrets`. Never written to disk. `.cache/` and `.venv/` are gitignored.
- Deviation from the spec's file list: an extra module `blm/export.py` holds the results-to-DataFrame/CSV/XLSX code so `matcher.py` stays IO-free.
- Commit after every task with a conventional-commit message ending in `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

---

## File Structure

| Path | Responsibility |
|---|---|
| `requirements.txt` | Runtime and test dependencies |
| `.gitignore` | `.venv/`, `.cache/`, `.streamlit/secrets.toml`, `__pycache__/` |
| `.streamlit/config.toml` | Theme and server defaults |
| `.streamlit/secrets.example.toml` | Documented empty secrets template |
| `blm/__init__.py` | Package marker, version string |
| `blm/models.py` | Dataclasses shared by all modules |
| `blm/ingest/frog_csv.py` | Screaming Frog embeddings CSV to `OwnPage` list |
| `blm/ingest/backlinks_csv.py` | Any broken-backlinks CSV/XLSX to `BrokenBacklink` list, column detection and manual mapping |
| `blm/ingest/ahrefs_api.py` | Optional live fetch from Ahrefs API v3 |
| `blm/ranking.py` | Filter, sort, cap, assign `value_rank` |
| `blm/cache.py` | JSON file cache under `.cache/` |
| `blm/wayback.py` | CDX lookup, raw snapshot fetch, text extraction, fallback text |
| `blm/embeddings/base.py` | Provider ABC with batching, split-on-error, `probe_dimension` |
| `blm/embeddings/openai.py`, `gemini.py`, `ollama.py` | One HTTP client each |
| `blm/embeddings/__init__.py` | `make_provider` factory and default model names |
| `blm/matcher.py` | Cosine similarity, top 3, content-gap flag, priority order |
| `blm/verify.py` | Live 404 and link-presence check |
| `blm/outreach.py` | Chat completion over HTTP and mail-draft prompt |
| `blm/export.py` | Results to DataFrame, CSV bytes, XLSX bytes |
| `app.py` | Streamlit UI, five sections |
| `tests/fixtures/*` | Small CSV/JSON/HTML samples |
| `tests/test_*.py` | One test file per module |
| `README.md` | German README with English summary |

---

### Task 1: Project scaffold and data model

**Files:**
- Create: `requirements.txt`, `.gitignore`, `.streamlit/config.toml`, `blm/__init__.py`, `blm/ingest/__init__.py`, `blm/embeddings/__init__.py` (empty for now), `blm/models.py`, `tests/__init__.py`, `tests/test_models.py`

**Interfaces:**
- Produces: `blm.models.BrokenBacklink`, `OwnPage`, `RecoveredContent`, `Match`, `MatchResult` (exact fields below). Every later task imports these.

- [ ] **Step 1: Create the environment**

```bash
cd /Users/Daniel/Downloads/broken-link-matcher
uv python install 3.11
uv venv --python 3.11 .venv
```

- [ ] **Step 2: Write requirements.txt and .gitignore**

`requirements.txt`:
```
streamlit>=1.38
httpx>=0.27
pandas>=2.2
numpy>=1.26
trafilatura>=1.12
beautifulsoup4>=4.12
lxml>=5.0
openpyxl>=3.1
pytest>=8.0
respx>=0.21
```

`.gitignore`:
```
.venv/
.cache/
__pycache__/
*.pyc
.pytest_cache/
.streamlit/secrets.toml
.DS_Store
```

`.streamlit/config.toml`:
```toml
[server]
headless = true
maxUploadSize = 500

[theme]
base = "light"
```

Install: `uv pip install -r requirements.txt`

- [ ] **Step 3: Write the failing test for the data model**

`tests/__init__.py`: empty file.

`tests/test_models.py`:
```python
import numpy as np

from blm.models import BrokenBacklink, Match, MatchResult, OwnPage, RecoveredContent


def test_broken_backlink_defaults():
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://b.de/dead")
    assert bl.anchor == ""
    assert bl.domain_rating is None
    assert bl.is_dofollow is None
    assert bl.value_rank is None


def test_match_result_defaults():
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://b.de/dead")
    rc = RecoveredContent(url_to=bl.url_to, text=None, source="none")
    mr = MatchResult(backlink=bl, recovered=rc)
    assert mr.top == []
    assert mr.is_content_gap is False
    assert mr.verification == "skipped"
    assert mr.errors == []


def test_own_page_holds_vector():
    p = OwnPage(url="https://me.de/x", vector=np.zeros(3, dtype=np.float32))
    assert p.vector.shape == (3,)
    assert p.title == ""
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blm'`

- [ ] **Step 5: Write the package and models**

`blm/__init__.py`:
```python
"""Broken Link Matcher: semantic broken-link building helper."""

__version__ = "0.1.0"
```

`blm/ingest/__init__.py` and `blm/embeddings/__init__.py`: empty files (the embeddings one is filled in Task 7).

`blm/models.py`:
```python
"""Dataclasses shared by every pipeline step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class BrokenBacklink:
    """One broken backlink pointing at a competitor URL."""

    url_from: str
    url_to: str
    anchor: str = ""
    snippet_left: str = ""
    snippet_right: str = ""
    title_from: str = ""
    domain_rating: Optional[float] = None
    url_rating: Optional[float] = None
    page_traffic: Optional[int] = None
    is_dofollow: Optional[bool] = None
    is_content: Optional[bool] = None
    http_code_target: Optional[int] = None
    value_rank: Optional[int] = None


@dataclass
class OwnPage:
    """One page of the user's own domain with its Screaming Frog embedding."""

    url: str
    vector: np.ndarray
    title: str = ""


@dataclass
class RecoveredContent:
    """Text recovered for a dead competitor URL.

    source is one of: "wayback", "fallback", "none".
    """

    url_to: str
    text: Optional[str]
    source: str
    snapshot_timestamp: Optional[str] = None
    error: Optional[str] = None


@dataclass
class Match:
    url: str
    score: float


@dataclass
class MatchResult:
    """Final row: backlink, recovered text, top matches and bookkeeping.

    verification is one of: "confirmed", "fixed", "unknown", "skipped".
    """

    backlink: BrokenBacklink
    recovered: RecoveredContent
    top: list[Match] = field(default_factory=list)
    is_content_gap: bool = False
    value_rank: int = 0
    priority: int = 0
    verification: str = "skipped"
    errors: list[str] = field(default_factory=list)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_models.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add requirements.txt .gitignore .streamlit/config.toml blm tests
git commit -m "feat: scaffold project and shared data model

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Screaming Frog embeddings parser

**Files:**
- Create: `blm/ingest/frog_csv.py`, `tests/fixtures/frog_wide.csv`, `tests/fixtures/frog_single_column.csv`, `tests/test_frog_csv.py`

**Interfaces:**
- Consumes: `blm.models.OwnPage`
- Produces: `load_frog_embeddings(source) -> FrogImport` where `FrogImport(pages: list[OwnPage], dimension: int, skipped: int)`. `source` is a file path or a file-like object (Streamlit upload).

Verified against a real Screaming Frog 24.3 export: the file has a `url` column followed by `embedding_0 ... embedding_N` columns, one float each, not normalised. A second format with a single list-valued column is supported defensively.

- [ ] **Step 1: Write fixtures**

`tests/fixtures/frog_wide.csv`:
```
url,embedding_0,embedding_1,embedding_2,embedding_3
https://me.de/kueche-aus-stahl,1.0,0.0,0.0,0.0
https://me.de/kochfeld-reinigen,0.0,1.0,0.0,0.0
https://me.de/dunstabzug-tipps,0.0,0.0,1.0,0.0
https://me.de/broken-row,0.0,abc,0.0,0.0
```

`tests/fixtures/frog_single_column.csv`:
```
Address,Title 1,Embeddings
https://me.de/a,Seite A,"[0.5, 0.5, 0.0]"
https://me.de/b,Seite B,"[0.0, 0.0, 1.0]"
https://me.de/c,Seite C,
```

- [ ] **Step 2: Write the failing tests**

`tests/test_frog_csv.py`:
```python
from pathlib import Path

import numpy as np
import pytest

from blm.ingest.frog_csv import load_frog_embeddings

FIX = Path(__file__).parent / "fixtures"


def test_wide_format_parses_urls_and_dimension():
    imp = load_frog_embeddings(FIX / "frog_wide.csv")
    assert imp.dimension == 4
    assert [p.url for p in imp.pages] == [
        "https://me.de/kueche-aus-stahl",
        "https://me.de/kochfeld-reinigen",
        "https://me.de/dunstabzug-tipps",
    ]
    assert imp.pages[0].vector.dtype == np.float32
    assert imp.pages[0].vector.tolist() == [1.0, 0.0, 0.0, 0.0]


def test_wide_format_skips_and_counts_broken_rows():
    imp = load_frog_embeddings(FIX / "frog_wide.csv")
    assert imp.skipped == 1


def test_single_column_format_with_titles():
    imp = load_frog_embeddings(FIX / "frog_single_column.csv")
    assert imp.dimension == 3
    assert imp.skipped == 1
    assert imp.pages[0].title == "Seite A"
    assert imp.pages[1].vector.tolist() == [0.0, 0.0, 1.0]


def test_missing_url_column_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("foo,embedding_0\nx,1.0\n")
    with pytest.raises(ValueError, match="URL"):
        load_frog_embeddings(f)


def test_no_vectors_raises(tmp_path):
    f = tmp_path / "bad.csv"
    f.write_text("url,other\nhttps://a.de,1\n")
    with pytest.raises(ValueError, match="Embedding"):
        load_frog_embeddings(f)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_frog_csv.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'blm.ingest.frog_csv'`

- [ ] **Step 4: Implement the parser**

`blm/ingest/frog_csv.py`:
```python
"""Parse the Screaming Frog embeddings export into OwnPage objects.

Two layouts are supported:
1. Wide (verified against SF 24.3): column ``url`` then ``embedding_0`` ...
   ``embedding_N`` with one float per column.
2. Single column: a URL column plus one column holding a list such as
   ``[0.1, 0.2, ...]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from blm.models import OwnPage

URL_CANDIDATES = ("url", "address", "adresse")
TITLE_CANDIDATES = ("title", "title 1", "titel")
VECTOR_CANDIDATES = ("embedding", "embeddings", "vector", "embedding vector")
_WIDE_RE = re.compile(r"embedding_(\d+)", re.IGNORECASE)


@dataclass
class FrogImport:
    pages: list[OwnPage]
    dimension: int
    skipped: int


def _find_column(columns: dict[str, str], candidates: tuple[str, ...]) -> Optional[str]:
    for cand in candidates:
        if cand in columns:
            return columns[cand]
    return None


def _parse_vector(raw) -> Optional[np.ndarray]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    text = str(raw).strip().strip("[]()")
    if not text:
        return None
    parts = [p for p in re.split(r"[,\s]+", text) if p]
    try:
        vec = np.asarray([float(p) for p in parts], dtype=np.float32)
    except ValueError:
        return None
    return vec if vec.size else None


def load_frog_embeddings(source) -> FrogImport:
    """Read a Screaming Frog embeddings CSV. Raises ValueError on unusable input."""
    df = pd.read_csv(source, encoding="utf-8-sig")
    columns = {str(c).strip().lower(): c for c in df.columns}

    url_col = _find_column(columns, URL_CANDIDATES)
    if url_col is None:
        raise ValueError("Keine URL-Spalte gefunden (erwartet 'url' oder 'Address').")
    title_col = _find_column(columns, TITLE_CANDIDATES)

    wide_cols = sorted(
        (c for c in df.columns if _WIDE_RE.fullmatch(str(c).strip())),
        key=lambda c: int(_WIDE_RE.fullmatch(str(c).strip()).group(1)),
    )
    vector_col = None if wide_cols else _find_column(columns, VECTOR_CANDIDATES)
    if not wide_cols and vector_col is None:
        raise ValueError(
            "Keine Embedding-Spalten gefunden (erwartet 'embedding_0 ...' oder eine Spalte 'Embeddings')."
        )

    pages: list[OwnPage] = []
    skipped = 0
    for _, row in df.iterrows():
        if wide_cols:
            values = pd.to_numeric(row[wide_cols], errors="coerce").to_numpy(dtype=np.float32)
            vec = None if np.isnan(values).any() else values
        else:
            vec = _parse_vector(row[vector_col])
        if vec is None:
            skipped += 1
            continue
        title = ""
        if title_col is not None and pd.notna(row[title_col]):
            title = str(row[title_col])
        pages.append(OwnPage(url=str(row[url_col]).strip(), vector=vec, title=title))

    if not pages:
        raise ValueError("Keine gültigen Embeddings in der Datei.")

    dimension = int(pages[0].vector.size)
    consistent = [p for p in pages if p.vector.size == dimension]
    skipped += len(pages) - len(consistent)
    return FrogImport(pages=consistent, dimension=dimension, skipped=skipped)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_frog_csv.py -v`
Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add blm/ingest/frog_csv.py tests/fixtures/frog_wide.csv tests/fixtures/frog_single_column.csv tests/test_frog_csv.py
git commit -m "feat: parse Screaming Frog embeddings export

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Broken-backlinks CSV/XLSX parser with column detection

**Files:**
- Create: `blm/ingest/backlinks_csv.py`, `tests/fixtures/ahrefs_ui_export.csv`, `tests/fixtures/ahrefs_api_export.csv`, `tests/fixtures/unknown_columns.csv`, `tests/test_backlinks_csv.py`

**Interfaces:**
- Consumes: `blm.models.BrokenBacklink`
- Produces:
  - `read_table(source, filename: str | None = None) -> pd.DataFrame`
  - `detect_columns(df) -> ColumnMapping` with `ColumnMapping(mapping: dict[str, str], missing: list[str], columns: list[str])`; `mapping` maps internal field name to source column name
  - `parse_backlinks(df, mapping: dict[str, str]) -> list[BrokenBacklink]`
  - `parse_bool(value) -> bool | None`
  - `REQUIRED_FIELDS = ("url_from", "url_to")`, `OPTIONAL_FIELDS` tuple, both used by the UI mapping form

The Ahrefs UI column names below are best-effort and marked for verification against a real export in Task 13; the alias table is the single place to extend.

- [ ] **Step 1: Write fixtures**

`tests/fixtures/ahrefs_ui_export.csv`:
```
Referring page title,Referring page URL,Domain rating,UR,Page traffic,Target URL,Left context,Anchor,Right context,Nofollow,Content,Target URL HTTP code
Beste Küchentipps,https://blog.example/kueche,72,35,1200,https://konkurrent.de/ratgeber/stahl,Wir empfehlen den,Ratgeber zu Stahlküchen,von Konkurrent.,No,Yes,404
Forum Thread,https://forum.example/t/1,40,10,,https://konkurrent.de/alt,,hier,,Yes,No,404
```

`tests/fixtures/ahrefs_api_export.csv`:
```
url_from,url_to,anchor,snippet_left,snippet_right,title,domain_rating_source,url_rating_source,http_code_target,is_dofollow,is_content,traffic
https://blog.example/kueche,https://konkurrent.de/ratgeber/stahl,Ratgeber zu Stahlküchen,Wir empfehlen den,von Konkurrent.,Beste Küchentipps,72.0,35.0,404,true,true,1200
```

`tests/fixtures/unknown_columns.csv`:
```
Quelle,Ziel,Text
https://x.de/a,https://y.de/b,hallo
```

- [ ] **Step 2: Write the failing tests**

`tests/test_backlinks_csv.py`:
```python
from pathlib import Path

import pytest

from blm.ingest.backlinks_csv import (
    REQUIRED_FIELDS,
    detect_columns,
    parse_backlinks,
    parse_bool,
    read_table,
)

FIX = Path(__file__).parent / "fixtures"


def test_detects_ahrefs_ui_columns():
    df = read_table(FIX / "ahrefs_ui_export.csv")
    cm = detect_columns(df)
    assert cm.missing == []
    assert cm.mapping["url_from"] == "Referring page URL"
    assert cm.mapping["url_to"] == "Target URL"
    assert cm.mapping["domain_rating"] == "Domain rating"
    assert cm.mapping["is_nofollow"] == "Nofollow"


def test_parses_ahrefs_ui_rows():
    df = read_table(FIX / "ahrefs_ui_export.csv")
    rows = parse_backlinks(df, detect_columns(df).mapping)
    assert len(rows) == 2
    r = rows[0]
    assert r.url_from == "https://blog.example/kueche"
    assert r.anchor == "Ratgeber zu Stahlküchen"
    assert r.domain_rating == 72.0
    assert r.page_traffic == 1200
    assert r.is_dofollow is True
    assert r.is_content is True
    assert r.http_code_target == 404
    assert rows[1].is_dofollow is False
    assert rows[1].page_traffic is None


def test_parses_ahrefs_api_schema():
    df = read_table(FIX / "ahrefs_api_export.csv")
    cm = detect_columns(df)
    assert cm.missing == []
    rows = parse_backlinks(df, cm.mapping)
    assert rows[0].title_from == "Beste Küchentipps"
    assert rows[0].is_dofollow is True
    assert rows[0].url_rating == 35.0


def test_unknown_columns_reports_missing_and_lists_columns():
    df = read_table(FIX / "unknown_columns.csv")
    cm = detect_columns(df)
    assert set(cm.missing) == set(REQUIRED_FIELDS)
    assert cm.columns == ["Quelle", "Ziel", "Text"]


def test_manual_mapping_works():
    df = read_table(FIX / "unknown_columns.csv")
    rows = parse_backlinks(df, {"url_from": "Quelle", "url_to": "Ziel", "anchor": "Text"})
    assert rows[0].url_to == "https://y.de/b"
    assert rows[0].anchor == "hallo"
    assert rows[0].domain_rating is None


def test_rows_without_urls_are_dropped():
    df = read_table(FIX / "unknown_columns.csv")
    df.loc[len(df)] = ["", "https://y.de/c", "x"]
    rows = parse_backlinks(df, {"url_from": "Quelle", "url_to": "Ziel"})
    assert len(rows) == 1


@pytest.mark.parametrize(
    "value,expected",
    [("Yes", True), ("ja", True), ("true", True), ("1", True), ("dofollow", True),
     ("No", False), ("nein", False), ("false", False), ("0", False), ("nofollow", False),
     ("", None), (None, None), (float("nan"), None), ("maybe", None)],
)
def test_parse_bool(value, expected):
    assert parse_bool(value) is expected


def test_read_xlsx(tmp_path):
    import pandas as pd

    p = tmp_path / "x.xlsx"
    pd.DataFrame({"Referring page URL": ["https://a.de"], "Target URL": ["https://b.de/x"]}).to_excel(p, index=False)
    df = read_table(p)
    assert list(df.columns) == ["Referring page URL", "Target URL"]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_backlinks_csv.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement the parser**

`blm/ingest/backlinks_csv.py`:
```python
"""Read a broken-backlinks table (Ahrefs UI export, Ahrefs API/MCP output, or any
other tool) and normalise it into BrokenBacklink objects.

Column detection is alias based. Extend FIELD_ALIASES to support more tools.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from blm.models import BrokenBacklink

REQUIRED_FIELDS = ("url_from", "url_to")
OPTIONAL_FIELDS = (
    "anchor",
    "snippet_left",
    "snippet_right",
    "title_from",
    "domain_rating",
    "url_rating",
    "page_traffic",
    "is_dofollow",
    "is_nofollow",
    "is_content",
    "http_code_target",
)

# internal field -> lower-cased source column names (Ahrefs UI export, Ahrefs API, misc.)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "url_from": ("url_from", "referring page url", "referring page", "source url", "source page url", "source"),
    "url_to": ("url_to", "target url", "target page url", "broken url", "destination url", "target"),
    "anchor": ("anchor", "anchor text", "ankertext", "link anchor"),
    "snippet_left": ("snippet_left", "left context", "text before", "context left"),
    "snippet_right": ("snippet_right", "right context", "text after", "context right"),
    "title_from": ("title", "referring page title", "source title", "page title", "referring title"),
    "domain_rating": ("domain_rating_source", "domain rating", "dr", "source dr", "referring domain rating"),
    "url_rating": ("url_rating_source", "url rating", "ur", "source ur"),
    "page_traffic": ("traffic", "page traffic", "referring page traffic", "organic traffic"),
    "is_dofollow": ("is_dofollow", "dofollow", "follow"),
    "is_nofollow": ("is_nofollow", "nofollow"),
    "is_content": ("is_content", "content", "in content"),
    "http_code_target": ("http_code_target", "target url http code", "target http code", "http code target", "target status"),
}

_TRUE = {"true", "1", "yes", "ja", "y", "dofollow", "follow", "x", "wahr"}
_FALSE = {"false", "0", "no", "nein", "n", "nofollow", "falsch"}


@dataclass
class ColumnMapping:
    mapping: dict[str, str]
    missing: list[str]
    columns: list[str]


def read_table(source, filename: Optional[str] = None) -> pd.DataFrame:
    """Read CSV or XLSX. `filename` is used for type detection when `source` is a stream."""
    name = (filename or getattr(source, "name", None) or str(source)).lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(source)
    return pd.read_csv(source, sep=None, engine="python", encoding="utf-8-sig", dtype=str, keep_default_na=False)


def detect_columns(df: pd.DataFrame) -> ColumnMapping:
    lowered = {str(c).strip().lower(): str(c) for c in df.columns}
    mapping: dict[str, str] = {}
    for field, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                mapping[field] = lowered[alias]
                break
    missing = [f for f in REQUIRED_FIELDS if f not in mapping]
    return ColumnMapping(mapping=mapping, missing=missing, columns=[str(c) for c in df.columns])


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def parse_bool(value) -> Optional[bool]:
    if _is_blank(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def _to_float(value) -> Optional[float]:
    if _is_blank(value):
        return None
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def _to_int(value) -> Optional[int]:
    f = _to_float(value)
    return None if f is None else int(f)


def _text(value) -> str:
    return "" if _is_blank(value) else str(value).strip()


def parse_backlinks(df: pd.DataFrame, mapping: dict[str, str]) -> list[BrokenBacklink]:
    """Build BrokenBacklink rows. Rows missing url_from or url_to are dropped."""
    for field in REQUIRED_FIELDS:
        if field not in mapping:
            raise ValueError(f"Pflichtfeld nicht zugeordnet: {field}")

    def col(row, field):
        name = mapping.get(field)
        return row[name] if name is not None and name in row.index else None

    rows: list[BrokenBacklink] = []
    for _, row in df.iterrows():
        url_from, url_to = _text(col(row, "url_from")), _text(col(row, "url_to"))
        if not url_from or not url_to:
            continue
        dofollow = parse_bool(col(row, "is_dofollow"))
        if dofollow is None:
            nofollow = parse_bool(col(row, "is_nofollow"))
            dofollow = None if nofollow is None else not nofollow
        rows.append(
            BrokenBacklink(
                url_from=url_from,
                url_to=url_to,
                anchor=_text(col(row, "anchor")),
                snippet_left=_text(col(row, "snippet_left")),
                snippet_right=_text(col(row, "snippet_right")),
                title_from=_text(col(row, "title_from")),
                domain_rating=_to_float(col(row, "domain_rating")),
                url_rating=_to_float(col(row, "url_rating")),
                page_traffic=_to_int(col(row, "page_traffic")),
                is_dofollow=dofollow,
                is_content=parse_bool(col(row, "is_content")),
                http_code_target=_to_int(col(row, "http_code_target")),
            )
        )
    return rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_backlinks_csv.py -v`
Expected: all passed (8 tests plus 14 parametrised cases)

- [ ] **Step 6: Commit**

```bash
git add blm/ingest/backlinks_csv.py tests/fixtures/ahrefs_ui_export.csv tests/fixtures/ahrefs_api_export.csv tests/fixtures/unknown_columns.csv tests/test_backlinks_csv.py
git commit -m "feat: parse broken-backlink exports with alias-based column detection

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Ranking (filter, sort, cap, value_rank)

**Files:**
- Create: `blm/ranking.py`, `tests/test_ranking.py`

**Interfaces:**
- Consumes: `BrokenBacklink`
- Produces: `rank_backlinks(backlinks, *, dofollow_only=True, content_only=True, min_dr=0.0, sort_by="domain_rating", limit=100) -> list[BrokenBacklink]` returning new objects with `value_rank` set from 1. `SORT_FIELDS = ("domain_rating", "url_rating", "page_traffic")`.

- [ ] **Step 1: Write the failing tests**

`tests/test_ranking.py`:
```python
from blm.models import BrokenBacklink
from blm.ranking import SORT_FIELDS, rank_backlinks


def bl(i, dr=None, ur=None, traffic=None, dofollow=None, content=None):
    return BrokenBacklink(
        url_from=f"https://s{i}.de/p", url_to=f"https://c.de/{i}", domain_rating=dr,
        url_rating=ur, page_traffic=traffic, is_dofollow=dofollow, is_content=content,
    )


def test_sorts_by_dr_then_traffic_with_none_last():
    rows = [bl(1, dr=50, traffic=10), bl(2, dr=70, traffic=1), bl(3, dr=None, traffic=999), bl(4, dr=70, traffic=500)]
    out = rank_backlinks(rows, dofollow_only=False, content_only=False)
    assert [r.url_to for r in out] == ["https://c.de/4", "https://c.de/2", "https://c.de/1", "https://c.de/3"]
    assert [r.value_rank for r in out] == [1, 2, 3, 4]


def test_filters_dofollow_and_content_but_keeps_none():
    rows = [bl(1, dofollow=False, content=True), bl(2, dofollow=True, content=False), bl(3, dofollow=None, content=None), bl(4, dofollow=True, content=True)]
    out = rank_backlinks(rows)
    assert sorted(r.url_to for r in out) == ["https://c.de/3", "https://c.de/4"]


def test_min_dr_drops_low_but_keeps_unknown():
    rows = [bl(1, dr=20), bl(2, dr=60), bl(3, dr=None)]
    out = rank_backlinks(rows, dofollow_only=False, content_only=False, min_dr=50)
    assert sorted(r.url_to for r in out) == ["https://c.de/2", "https://c.de/3"]


def test_sort_by_traffic_and_limit():
    rows = [bl(1, dr=90, traffic=5), bl(2, dr=10, traffic=500), bl(3, dr=50, traffic=100)]
    out = rank_backlinks(rows, dofollow_only=False, content_only=False, sort_by="page_traffic", limit=2)
    assert [r.url_to for r in out] == ["https://c.de/2", "https://c.de/3"]


def test_does_not_mutate_input():
    rows = [bl(1, dr=1)]
    rank_backlinks(rows, dofollow_only=False, content_only=False)
    assert rows[0].value_rank is None


def test_sort_fields_constant():
    assert SORT_FIELDS == ("domain_rating", "url_rating", "page_traffic")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ranking.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement ranking**

`blm/ranking.py`:
```python
"""Prioritise linking pages: filter, sort, cap, and assign value_rank."""

from __future__ import annotations

from dataclasses import replace

from blm.models import BrokenBacklink

SORT_FIELDS = ("domain_rating", "url_rating", "page_traffic")


def _desc_key(value):
    """Sort key for descending order with None last."""
    return (value is None, -(value or 0))


def rank_backlinks(
    backlinks: list[BrokenBacklink],
    *,
    dofollow_only: bool = True,
    content_only: bool = True,
    min_dr: float = 0.0,
    sort_by: str = "domain_rating",
    limit: int = 100,
) -> list[BrokenBacklink]:
    if sort_by not in SORT_FIELDS:
        raise ValueError(f"Unbekanntes Sortierkriterium: {sort_by}")

    kept = []
    for bl in backlinks:
        if dofollow_only and bl.is_dofollow is False:
            continue
        if content_only and bl.is_content is False:
            continue
        if min_dr > 0 and bl.domain_rating is not None and bl.domain_rating < min_dr:
            continue
        kept.append(bl)

    kept.sort(key=lambda b: (_desc_key(getattr(b, sort_by)), _desc_key(b.page_traffic)))
    return [replace(b, value_rank=i + 1) for i, b in enumerate(kept[:limit])]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ranking.py -v`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add blm/ranking.py tests/test_ranking.py
git commit -m "feat: rank backlinks by link value with filters and cap

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: JSON file cache

**Files:**
- Create: `blm/cache.py`, `tests/test_cache.py`

**Interfaces:**
- Produces: `JsonCache(root: Path = Path(".cache"))` with `get(namespace: str, key: str) -> dict | None`, `set(namespace: str, key: str, value: dict) -> None`, `clear() -> int` (number of files removed). Keys are hashed with SHA-256 so any string works.

- [ ] **Step 1: Write the failing tests**

`tests/test_cache.py`:
```python
from blm.cache import JsonCache


def test_roundtrip(tmp_path):
    c = JsonCache(tmp_path / "c")
    assert c.get("wayback", "https://x.de/a") is None
    c.set("wayback", "https://x.de/a", {"text": "hallo", "n": 1})
    assert c.get("wayback", "https://x.de/a") == {"text": "hallo", "n": 1}


def test_namespaces_and_keys_are_independent(tmp_path):
    c = JsonCache(tmp_path)
    c.set("emb", "openai|text-embedding-3-small|hallo", {"v": [1.0]})
    assert c.get("emb", "openai|text-embedding-3-large|hallo") is None
    assert c.get("wayback", "openai|text-embedding-3-small|hallo") is None


def test_clear_removes_everything(tmp_path):
    c = JsonCache(tmp_path)
    c.set("a", "1", {"x": 1})
    c.set("b", "2", {"x": 2})
    assert c.clear() == 2
    assert c.get("a", "1") is None


def test_corrupt_file_is_treated_as_miss(tmp_path):
    c = JsonCache(tmp_path)
    c.set("a", "1", {"x": 1})
    path = next((tmp_path / "a").iterdir())
    path.write_text("{not json")
    assert c.get("a", "1") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_cache.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the cache**

`blm/cache.py`:
```python
"""Tiny JSON-per-entry file cache used for Wayback texts and embeddings."""

from __future__ import annotations

import hashlib
import json
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
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, namespace: str, key: str, value: dict) -> None:
        path = self._path(namespace, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> int:
        if not self.root.exists():
            return 0
        removed = 0
        for file in self.root.rglob("*.json"):
            file.unlink()
            removed += 1
        return removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_cache.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add blm/cache.py tests/test_cache.py
git commit -m "feat: add JSON file cache

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Wayback recovery (CDX lookup, raw fetch, extraction, fallback)

**Files:**
- Create: `blm/wayback.py`, `tests/fixtures/cdx_hit.json`, `tests/fixtures/archived_page.html`, `tests/test_wayback.py`

**Interfaces:**
- Consumes: `BrokenBacklink`, `RecoveredContent`, `JsonCache`
- Produces:
  - `recover_content(backlink, client: httpx.Client, cache: JsonCache | None, *, max_chars=12000, sleeper=time.sleep) -> RecoveredContent`
  - `latest_snapshot(url, client, sleeper) -> tuple[str, str] | None` (timestamp, original URL)
  - `snapshot_url(timestamp, original) -> str`
  - `extract_text(html) -> str`
  - `fallback_text(backlink) -> str | None`
  - `slug_words(url) -> str`
  - `USER_AGENT` constant, `class WaybackError(Exception)`
- Rate limiting is the caller's job between rows (app sleeps 1 s between URLs); retries inside this module use the injected `sleeper` so tests run instantly.

- [ ] **Step 1: Write fixtures**

`tests/fixtures/cdx_hit.json`:
```json
[["timestamp","original"],["20240315120000","https://konkurrent.de/ratgeber/stahl"]]
```

`tests/fixtures/archived_page.html`:
```html
<!doctype html>
<html lang="de"><head><title>Stahlküchen Ratgeber</title></head>
<body>
<nav><a href="/">Start</a><a href="/kontakt">Kontakt</a></nav>
<main>
<h1>Küchen aus Edelstahl: Vorteile und Pflege</h1>
<p>Edelstahl ist hygienisch, hitzebeständig und langlebig. In diesem Ratgeber zeigen wir, worauf es bei der Planung einer Stahlküche ankommt und wie Sie die Oberfläche richtig pflegen.</p>
<p>Fingerabdrücke lassen sich mit einem Mikrofasertuch und etwas Spülmittel entfernen. Kratzer vermeiden Sie, indem Sie Schneidebretter verwenden.</p>
</main>
<footer>Impressum</footer>
</body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_wayback.py`:
```python
import json
from pathlib import Path

import httpx
import pytest
import respx

from blm.cache import JsonCache
from blm.models import BrokenBacklink
from blm.wayback import (
    CDX_URL,
    WaybackError,
    extract_text,
    fallback_text,
    latest_snapshot,
    recover_content,
    slug_words,
    snapshot_url,
)

FIX = Path(__file__).parent / "fixtures"
CDX_HIT = json.loads((FIX / "cdx_hit.json").read_text())
HTML = (FIX / "archived_page.html").read_text()
DEAD = "https://konkurrent.de/ratgeber/stahl"


def no_sleep(_seconds):
    pass


def bl(**kw):
    base = dict(url_from="https://blog.example/kueche", url_to=DEAD)
    base.update(kw)
    return BrokenBacklink(**base)


def test_snapshot_url_uses_id_flag():
    assert snapshot_url("20240315120000", DEAD) == f"https://web.archive.org/web/20240315120000id_/{DEAD}"


@respx.mock
def test_latest_snapshot_requests_newest_200():
    route = respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    with httpx.Client() as client:
        ts, original = latest_snapshot(DEAD, client, sleeper=no_sleep)
    assert (ts, original) == ("20240315120000", DEAD)
    params = route.calls.last.request.url.params
    assert params["filter"] == "statuscode:200"
    assert params["limit"] == "-1"
    assert params["url"] == DEAD


@respx.mock
def test_latest_snapshot_none_when_no_rows():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[["timestamp", "original"]]))
    with httpx.Client() as client:
        assert latest_snapshot(DEAD, client, sleeper=no_sleep) is None


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(CDX_URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json=CDX_HIT)])
    with httpx.Client() as client:
        assert latest_snapshot(DEAD, client, sleeper=no_sleep) is not None
    assert route.call_count == 2


@respx.mock
def test_gives_up_after_three_retries():
    respx.get(CDX_URL).mock(return_value=httpx.Response(503))
    with httpx.Client() as client, pytest.raises(WaybackError):
        latest_snapshot(DEAD, client, sleeper=no_sleep)


def test_extract_text_returns_main_content_only():
    text = extract_text(HTML)
    assert "Edelstahl ist hygienisch" in text
    assert "Impressum" not in text


def test_slug_words():
    assert slug_words("https://konkurrent.de/ratgeber/stahl-kueche_pflege.html?x=1") == "ratgeber stahl kueche pflege"


def test_fallback_text_concatenates_existing_fields_only():
    text = fallback_text(bl(title_from="Beste Küchentipps", anchor="Ratgeber zu Stahlküchen", snippet_left="Wir empfehlen den", snippet_right="von Konkurrent."))
    assert text == "Beste Küchentipps. Ratgeber zu Stahlküchen. Wir empfehlen den. von Konkurrent. ratgeber stahl"


def test_fallback_text_none_when_nothing_available():
    assert fallback_text(BrokenBacklink(url_from="https://a.de", url_to="https://b.de/")) is None


@respx.mock
def test_recover_content_from_wayback_and_caches(tmp_path):
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    page = respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    cache = JsonCache(tmp_path)
    with httpx.Client() as client:
        rc = recover_content(bl(), client, cache, sleeper=no_sleep)
        assert rc.source == "wayback"
        assert rc.snapshot_timestamp == "20240315120000"
        assert "Edelstahl" in rc.text
        rc2 = recover_content(bl(), client, cache, sleeper=no_sleep)
    assert rc2.text == rc.text
    assert page.call_count == 1


@respx.mock
def test_recover_content_falls_back_when_unarchived():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[["timestamp", "original"]]))
    with httpx.Client() as client:
        rc = recover_content(bl(anchor="Stahlküchen Guide"), client, None, sleeper=no_sleep)
    assert rc.source == "fallback"
    assert rc.text == "Stahlküchen Guide. ratgeber stahl"
    assert rc.snapshot_timestamp is None


@respx.mock
def test_recover_content_none_when_unarchived_and_no_fields():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=[]))
    with httpx.Client() as client:
        rc = recover_content(BrokenBacklink(url_from="https://a.de", url_to="https://b.de/"), client, None, sleeper=no_sleep)
    assert rc.source == "none"
    assert rc.text is None


@respx.mock
def test_recover_content_records_error_on_wayback_failure():
    respx.get(CDX_URL).mock(return_value=httpx.Response(500))
    with httpx.Client() as client:
        rc = recover_content(bl(anchor="x"), client, None, sleeper=no_sleep)
    assert rc.source == "fallback"
    assert "Wayback" in rc.error


@respx.mock
def test_text_is_capped():
    respx.get(CDX_URL).mock(return_value=httpx.Response(200, json=CDX_HIT))
    respx.get(snapshot_url("20240315120000", DEAD)).mock(return_value=httpx.Response(200, text=HTML))
    with httpx.Client() as client:
        rc = recover_content(bl(), client, None, max_chars=40, sleeper=no_sleep)
    assert len(rc.text) == 40
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_wayback.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement wayback**

`blm/wayback.py`:
```python
"""Recover the content of a dead URL from the Wayback Machine.

Always uses the newest snapshot with HTTP status 200. Fetches the raw archived
HTML with the ``id_`` flag so no Wayback toolbar or rewritten links end up in
the text. Falls back to a plain concatenation of fields Ahrefs already
delivered; nothing is generated.
"""

from __future__ import annotations

import re
import time
from dataclasses import asdict
from typing import Callable, Optional
from urllib.parse import unquote, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from blm.cache import JsonCache
from blm.models import BrokenBacklink, RecoveredContent

CDX_URL = "https://web.archive.org/cdx/search/cdx"
USER_AGENT = "broken-link-matcher/0.1 (SEO research tool; polite crawler, 1 req/s)"
RETRY_PAUSES = (2, 4, 8)
_EXT_RE = re.compile(r"\.(html?|php|aspx?|jsp)$", re.IGNORECASE)


class WaybackError(Exception):
    pass


def _get_with_retry(client: httpx.Client, url: str, params: Optional[dict], sleeper: Callable[[float], None]) -> httpx.Response:
    last_error = "unknown"
    for attempt in range(len(RETRY_PAUSES) + 1):
        try:
            resp = client.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30.0, follow_redirects=True)
        except httpx.TransportError as exc:
            last_error = str(exc)
        else:
            if resp.status_code == 429 or resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
            else:
                return resp
        if attempt < len(RETRY_PAUSES):
            sleeper(RETRY_PAUSES[attempt])
    raise WaybackError(f"Wayback request failed after retries: {last_error}")


def latest_snapshot(url: str, client: httpx.Client, sleeper: Callable[[float], None] = time.sleep) -> Optional[tuple[str, str]]:
    """Return (timestamp, original_url) of the newest 200 snapshot, or None."""
    params = {"url": url, "output": "json", "filter": "statuscode:200", "fl": "timestamp,original", "limit": "-1"}
    resp = _get_with_retry(client, CDX_URL, params, sleeper)
    if resp.status_code != 200 or not resp.content.strip():
        return None
    rows = resp.json()
    if len(rows) < 2:
        return None
    timestamp, original = rows[-1][0], rows[-1][1]
    return str(timestamp), str(original)


def snapshot_url(timestamp: str, original: str) -> str:
    return f"https://web.archive.org/web/{timestamp}id_/{original}"


def extract_text(html: str) -> str:
    text = trafilatura.extract(html, include_comments=False, include_tables=True, favor_recall=True)
    if text and text.strip():
        return text.strip()
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header"]):
        tag.decompose()
    body = soup.body or soup
    return body.get_text(" ", strip=True)


def slug_words(url: str) -> str:
    path = unquote(urlparse(url).path)
    path = _EXT_RE.sub("", path)
    words = re.sub(r"[-_/.+]+", " ", path)
    return re.sub(r"\s+", " ", words).strip()


def fallback_text(backlink: BrokenBacklink) -> Optional[str]:
    """Concatenate fields Ahrefs already delivered. Returns None if all are empty."""
    parts = [p.strip() for p in (backlink.title_from, backlink.anchor, backlink.snippet_left, backlink.snippet_right) if p and p.strip()]
    slug = slug_words(backlink.url_to)
    if slug:
        parts.append(slug)
    if not parts:
        return None
    return ". ".join(p.rstrip(".") for p in parts)


def recover_content(
    backlink: BrokenBacklink,
    client: httpx.Client,
    cache: Optional[JsonCache],
    *,
    max_chars: int = 12000,
    sleeper: Callable[[float], None] = time.sleep,
) -> RecoveredContent:
    url = backlink.url_to
    if cache is not None:
        hit = cache.get("wayback", url)
        if hit is not None:
            return RecoveredContent(**hit)

    error: Optional[str] = None
    try:
        snap = latest_snapshot(url, client, sleeper)
        if snap is not None:
            timestamp, original = snap
            resp = _get_with_retry(client, snapshot_url(timestamp, original), None, sleeper)
            text = extract_text(resp.text)[:max_chars] if resp.status_code == 200 else ""
            if text:
                result = RecoveredContent(url_to=url, text=text, source="wayback", snapshot_timestamp=timestamp)
                if cache is not None:
                    cache.set("wayback", url, asdict(result))
                return result
            error = "Snapshot ohne extrahierbaren Text"
        else:
            error = "Kein Snapshot mit Status 200"
    except WaybackError as exc:
        error = f"Wayback-Fehler: {exc}"

    fallback = fallback_text(backlink)
    if fallback is None:
        return RecoveredContent(url_to=url, text=None, source="none", error=error)
    return RecoveredContent(url_to=url, text=fallback[:max_chars], source="fallback", error=error)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_wayback.py -v`
Expected: 14 passed. If `test_extract_text_returns_main_content_only` fails because trafilatura keeps "Impressum", drop `favor_recall=True`; if it fails because trafilatura returns None for the short fixture, the BeautifulSoup fallback (which strips footer) must produce the expected text, so check the fixture footer is inside `<footer>`.

- [ ] **Step 6: Commit**

```bash
git add blm/wayback.py tests/fixtures/cdx_hit.json tests/fixtures/archived_page.html tests/test_wayback.py
git commit -m "feat: recover dead-page content from the Wayback Machine

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Embedding providers (OpenAI, Gemini, Ollama)

**Files:**
- Create: `blm/embeddings/base.py`, `blm/embeddings/openai.py`, `blm/embeddings/gemini.py`, `blm/embeddings/ollama.py`
- Modify: `blm/embeddings/__init__.py` (factory)
- Create: `tests/test_embeddings.py`

**Interfaces:**
- Produces:
  - `EmbeddingProvider` (ABC) with `name: str`, `model: str`, `batch_size: int`, `embed(texts: list[str]) -> list[np.ndarray | None]` (None for texts that failed even alone), `probe_dimension() -> int`
  - `EmbeddingError(Exception)`
  - `make_provider(name: str, model: str, *, api_key: str | None = None, base_url: str | None = None, client: httpx.Client | None = None) -> EmbeddingProvider`
  - `PROVIDERS = ("openai", "gemini", "ollama")`, `DEFAULT_EMBED_MODELS = {"openai": "text-embedding-3-small", "gemini": "gemini-embedding-001", "ollama": "nomic-embed-text"}`
- Endpoints: OpenAI `POST https://api.openai.com/v1/embeddings`; Gemini `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents?key=KEY`; Ollama `POST {base_url}/api/embed` (default base_url `http://localhost:11434`).

- [ ] **Step 1: Write the failing tests**

`tests/test_embeddings.py`:
```python
import httpx
import numpy as np
import pytest
import respx

from blm.embeddings import DEFAULT_EMBED_MODELS, PROVIDERS, make_provider
from blm.embeddings.base import EmbeddingError, EmbeddingProvider

OPENAI_URL = "https://api.openai.com/v1/embeddings"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:batchEmbedContents"
OLLAMA_URL = "http://localhost:11434/api/embed"


def test_constants():
    assert PROVIDERS == ("openai", "gemini", "ollama")
    assert set(DEFAULT_EMBED_MODELS) == set(PROVIDERS)


def test_unknown_provider():
    with pytest.raises(ValueError):
        make_provider("cohere", "x")


@respx.mock
def test_openai_embeds_in_order_and_sends_auth():
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json={
        "data": [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]}))
    p = make_provider("openai", "text-embedding-3-small", api_key="sk-test")
    vecs = p.embed(["a", "b"])
    assert vecs[0].tolist() == [1.0, 0.0] and vecs[1].tolist() == [0.0, 1.0]
    assert vecs[0].dtype == np.float32
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer sk-test"
    assert b'"model": "text-embedding-3-small"' in req.content or b'"model":"text-embedding-3-small"' in req.content


@respx.mock
def test_gemini_embeds_and_uses_key_param():
    route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(200, json={
        "embeddings": [{"values": [0.1, 0.2, 0.3]}]}))
    p = make_provider("gemini", "gemini-embedding-001", api_key="g-test")
    vecs = p.embed(["hallo"])
    assert vecs[0].shape == (3,)
    assert route.calls.last.request.url.params["key"] == "g-test"


@respx.mock
def test_ollama_embeds_with_custom_base_url():
    respx.post("http://ollama.local:11434/api/embed").mock(return_value=httpx.Response(200, json={
        "embeddings": [[0.5, 0.5]]}))
    p = make_provider("ollama", "nomic-embed-text", base_url="http://ollama.local:11434")
    assert p.embed(["x"])[0].tolist() == [0.5, 0.5]


@respx.mock
def test_probe_dimension():
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * 1536}]}))
    p = make_provider("openai", "text-embedding-3-small", api_key="k")
    assert p.probe_dimension() == 1536


@respx.mock
def test_batches_and_splits_on_error():
    calls = []

    def handler(request):
        import json
        body = json.loads(request.content)
        inputs = body["input"]
        calls.append(len(inputs))
        if "BAD" in inputs and len(inputs) > 1:
            return httpx.Response(400, json={"error": "too long"})
        if inputs == ["BAD"]:
            return httpx.Response(400, json={"error": "too long"})
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [float(i)]} for i in range(len(inputs))]})

    respx.post(OPENAI_URL).mock(side_effect=handler)
    p = make_provider("openai", "m", api_key="k")
    p.batch_size = 2
    vecs = p.embed(["a", "BAD", "c"])
    assert vecs[0] is not None and vecs[2] is not None
    assert vecs[1] is None
    assert calls[0] == 2  # first batch of two, then split


@respx.mock
def test_auth_error_raises_embedding_error_immediately():
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    p = make_provider("openai", "m", api_key="wrong")
    with pytest.raises(EmbeddingError, match="401"):
        p.probe_dimension()


def test_base_is_abstract():
    with pytest.raises(TypeError):
        EmbeddingProvider("m")  # type: ignore[abstract]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_embeddings.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Implement base**

`blm/embeddings/base.py`:
```python
"""Provider-agnostic embedding interface with batching and split-on-error."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import httpx
import numpy as np


class EmbeddingError(Exception):
    pass


class EmbeddingProvider(ABC):
    name: str = "base"
    batch_size: int = 32

    def __init__(self, model: str, client: Optional[httpx.Client] = None):
        self.model = model
        self.client = client or httpx.Client(timeout=60.0)

    @abstractmethod
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch. Raise EmbeddingError on any failure."""

    def _embed_split(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        try:
            return [np.asarray(v, dtype=np.float32) for v in self._embed_batch(texts)]
        except EmbeddingError as exc:
            if len(texts) == 1:
                return [None]
            if _is_auth_error(exc):
                raise
            mid = len(texts) // 2
            return self._embed_split(texts[:mid]) + self._embed_split(texts[mid:])

    def embed(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        out: list[Optional[np.ndarray]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(self._embed_split(texts[start : start + self.batch_size]))
        return out

    def probe_dimension(self) -> int:
        return len(self._embed_batch(["Dimensionstest"])[0])


def _is_auth_error(exc: Exception) -> bool:
    return "401" in str(exc) or "403" in str(exc)


def raise_for_status(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 400:
        raise EmbeddingError(f"{provider}: HTTP {resp.status_code}: {resp.text[:300]}")
```

- [ ] **Step 4: Implement the three providers and the factory**

`blm/embeddings/openai.py`:
```python
from __future__ import annotations

from typing import Optional

import httpx

from blm.embeddings.base import EmbeddingError, EmbeddingProvider, raise_for_status

OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"


class OpenAIEmbeddings(EmbeddingProvider):
    name = "openai"
    batch_size = 64

    def __init__(self, model: str, api_key: str, client: Optional[httpx.Client] = None):
        super().__init__(model, client)
        if not api_key:
            raise EmbeddingError("openai: API-Schlüssel fehlt")
        self.api_key = api_key

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self.client.post(
                OPENAI_EMBED_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"openai: {exc}") from exc
        raise_for_status(resp, "openai")
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
```

`blm/embeddings/gemini.py`:
```python
from __future__ import annotations

from typing import Optional

import httpx

from blm.embeddings.base import EmbeddingError, EmbeddingProvider, raise_for_status

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiEmbeddings(EmbeddingProvider):
    name = "gemini"
    batch_size = 32

    def __init__(self, model: str, api_key: str, client: Optional[httpx.Client] = None):
        super().__init__(model, client)
        if not api_key:
            raise EmbeddingError("gemini: API-Schlüssel fehlt")
        self.api_key = api_key

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        url = f"{GEMINI_BASE}/{self.model}:batchEmbedContents"
        body = {"requests": [{"model": f"models/{self.model}", "content": {"parts": [{"text": t}]}} for t in texts]}
        try:
            resp = self.client.post(url, params={"key": self.api_key}, json=body)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"gemini: {exc}") from exc
        raise_for_status(resp, "gemini")
        return [e["values"] for e in resp.json()["embeddings"]]
```

`blm/embeddings/ollama.py`:
```python
from __future__ import annotations

from typing import Optional

import httpx

from blm.embeddings.base import EmbeddingError, EmbeddingProvider, raise_for_status

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaEmbeddings(EmbeddingProvider):
    name = "ollama"
    batch_size = 16

    def __init__(self, model: str, base_url: Optional[str] = None, client: Optional[httpx.Client] = None):
        super().__init__(model, client)
        self.base_url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self.client.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": texts})
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"ollama: {exc}") from exc
        raise_for_status(resp, "ollama")
        return resp.json()["embeddings"]
```

`blm/embeddings/__init__.py`:
```python
"""Embedding providers. Pick one that matches the Screaming Frog configuration."""

from __future__ import annotations

from typing import Optional

import httpx

from blm.embeddings.base import EmbeddingError, EmbeddingProvider
from blm.embeddings.gemini import GeminiEmbeddings
from blm.embeddings.ollama import OllamaEmbeddings
from blm.embeddings.openai import OpenAIEmbeddings

PROVIDERS = ("openai", "gemini", "ollama")
DEFAULT_EMBED_MODELS = {
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
    "ollama": "nomic-embed-text",
}


def make_provider(
    name: str,
    model: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> EmbeddingProvider:
    if name == "openai":
        return OpenAIEmbeddings(model, api_key or "", client)
    if name == "gemini":
        return GeminiEmbeddings(model, api_key or "", client)
    if name == "ollama":
        return OllamaEmbeddings(model, base_url, client)
    raise ValueError(f"Unbekannter Embedding-Anbieter: {name}")


__all__ = ["PROVIDERS", "DEFAULT_EMBED_MODELS", "EmbeddingError", "EmbeddingProvider", "make_provider"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_embeddings.py -v`
Expected: 10 passed

- [ ] **Step 6: Commit**

```bash
git add blm/embeddings tests/test_embeddings.py
git commit -m "feat: add OpenAI, Gemini and Ollama embedding providers

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Matcher (cosine similarity, top 3, content gap, priority)

**Files:**
- Create: `blm/matcher.py`, `tests/test_matcher.py`

**Interfaces:**
- Consumes: `BrokenBacklink`, `RecoveredContent`, `OwnPage`, `Match`, `MatchResult`
- Produces:
  - `normalize_rows(m: np.ndarray) -> np.ndarray`
  - `top_k(query: np.ndarray, own_matrix: np.ndarray, urls: list[str], k: int = 3) -> list[Match]` (own_matrix already normalised)
  - `build_results(ranked: list[BrokenBacklink], recovered: list[RecoveredContent], vectors: list[np.ndarray | None], own_pages: list[OwnPage], *, threshold: float = 0.5, match_fallback: bool = True) -> list[MatchResult]` returning rows sorted by `priority`
- Priority order: matched non-gaps by value_rank, then content gaps by value_rank, then unmatched rows (no text, excluded fallback, embedding failure) by value_rank.

- [ ] **Step 1: Write the failing tests**

`tests/test_matcher.py`:
```python
import numpy as np

from blm.matcher import build_results, normalize_rows, top_k
from blm.models import BrokenBacklink, OwnPage, RecoveredContent


def own():
    return [
        OwnPage("https://me.de/stahl", np.array([2.0, 0.0, 0.0], dtype=np.float32)),
        OwnPage("https://me.de/holz", np.array([0.0, 3.0, 0.0], dtype=np.float32)),
        OwnPage("https://me.de/glas", np.array([0.0, 0.0, 1.0], dtype=np.float32)),
        OwnPage("https://me.de/mix", np.array([1.0, 1.0, 0.0], dtype=np.float32)),
    ]


def bl(i, rank):
    return BrokenBacklink(url_from=f"https://s{i}.de", url_to=f"https://c.de/{i}", value_rank=rank)


def test_normalize_rows_unit_length_and_zero_safe():
    m = normalize_rows(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert np.allclose(np.linalg.norm(m[0]), 1.0)
    assert m[1].tolist() == [0.0, 0.0]


def test_top_k_orders_by_cosine():
    pages = own()
    matrix = normalize_rows(np.stack([p.vector for p in pages]))
    hits = top_k(np.array([1.0, 0.1, 0.0]), matrix, [p.url for p in pages], k=3)
    assert [h.url for h in hits] == ["https://me.de/stahl", "https://me.de/mix", "https://me.de/holz"]
    assert hits[0].score > hits[1].score > hits[2].score
    assert 0.99 < hits[0].score <= 1.0


def test_top_k_respects_fewer_pages_than_k():
    matrix = normalize_rows(np.array([[1.0, 0.0]]))
    assert len(top_k(np.array([1.0, 0.0]), matrix, ["u"], k=3)) == 1


def test_build_results_flags_gap_and_orders_priority():
    ranked = [bl(1, 1), bl(2, 2), bl(3, 3), bl(4, 4)]
    recovered = [
        RecoveredContent("https://c.de/1", "t", "wayback"),
        RecoveredContent("https://c.de/2", "t", "wayback"),
        RecoveredContent("https://c.de/3", None, "none"),
        RecoveredContent("https://c.de/4", "t", "fallback"),
    ]
    vectors = [
        np.array([0.0, 0.0, 1.0]),   # matches glas perfectly
        np.array([1.0, 1.0, 1.0]),   # best cosine ~0.816 with mix -> above 0.5, no gap
        None,
        np.array([0.0, 1.0, 0.0]),   # fallback, matches holz
    ]
    out = build_results(ranked, recovered, vectors, own(), threshold=0.9)
    # row2 best score 0.816 < 0.9 -> gap; row3 unmatched; row4 fallback matched (holz 1.0)
    assert [r.backlink.url_to for r in out] == ["https://c.de/1", "https://c.de/4", "https://c.de/2", "https://c.de/3"]
    assert [r.priority for r in out] == [1, 2, 3, 4]
    assert out[0].top[0].url == "https://me.de/glas"
    assert out[2].is_content_gap is True
    assert out[3].top == [] and out[3].is_content_gap is False
    assert any("kein Text" in e for e in out[3].errors)


def test_build_results_can_exclude_fallback_rows():
    ranked = [bl(1, 1)]
    recovered = [RecoveredContent("https://c.de/1", "t", "fallback")]
    out = build_results(ranked, recovered, [np.array([1.0, 0.0, 0.0])], own(), match_fallback=False)
    assert out[0].top == []
    assert any("Fallback" in e for e in out[0].errors)


def test_build_results_handles_failed_embedding():
    ranked = [bl(1, 1)]
    recovered = [RecoveredContent("https://c.de/1", "t", "wayback")]
    out = build_results(ranked, recovered, [None], own())
    assert out[0].top == []
    assert any("Embedding" in e for e in out[0].errors)


def test_build_results_length_mismatch_raises():
    import pytest
    with pytest.raises(ValueError):
        build_results([bl(1, 1)], [], [], own())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_matcher.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement matcher**

`blm/matcher.py`:
```python
"""Cosine-similarity matching of recovered competitor texts against own pages.

Pure numpy and sorting; no IO.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from blm.models import BrokenBacklink, Match, MatchResult, OwnPage, RecoveredContent


def normalize_rows(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def top_k(query: np.ndarray, own_matrix: np.ndarray, urls: list[str], k: int = 3) -> list[Match]:
    q = np.asarray(query, dtype=np.float32)
    norm = np.linalg.norm(q)
    if norm == 0:
        return []
    scores = own_matrix @ (q / norm)
    k = min(k, len(urls))
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]
    return [Match(url=urls[i], score=float(scores[i])) for i in idx]


def build_results(
    ranked: list[BrokenBacklink],
    recovered: list[RecoveredContent],
    vectors: list[Optional[np.ndarray]],
    own_pages: list[OwnPage],
    *,
    threshold: float = 0.5,
    match_fallback: bool = True,
) -> list[MatchResult]:
    if not (len(ranked) == len(recovered) == len(vectors)):
        raise ValueError("ranked, recovered und vectors müssen gleich lang sein")

    own_matrix = normalize_rows(np.stack([p.vector for p in own_pages]))
    urls = [p.url for p in own_pages]

    matched: list[MatchResult] = []
    gaps: list[MatchResult] = []
    unmatched: list[MatchResult] = []
    for bl, rc, vec in zip(ranked, recovered, vectors):
        row = MatchResult(backlink=bl, recovered=rc, value_rank=bl.value_rank or 0)
        if rc.error:
            row.errors.append(rc.error)
        if rc.text is None:
            row.errors.append("Nicht gematcht: kein Text (kein Snapshot, keine Ahrefs-Felder)")
            unmatched.append(row)
            continue
        if rc.source == "fallback" and not match_fallback:
            row.errors.append("Nicht gematcht: Fallback-Zeilen sind ausgeschlossen")
            unmatched.append(row)
            continue
        if vec is None:
            row.errors.append("Nicht gematcht: Embedding fehlgeschlagen")
            unmatched.append(row)
            continue
        row.top = top_k(vec, own_matrix, urls, k=3)
        best = row.top[0].score if row.top else 0.0
        row.is_content_gap = best < threshold
        (gaps if row.is_content_gap else matched).append(row)

    ordered = sorted(matched, key=lambda r: r.value_rank) + sorted(gaps, key=lambda r: r.value_rank) + sorted(unmatched, key=lambda r: r.value_rank)
    for i, row in enumerate(ordered, start=1):
        row.priority = i
    return ordered
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_matcher.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add blm/matcher.py tests/test_matcher.py
git commit -m "feat: cosine matcher with content-gap flag and priority order

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Live verification

**Files:**
- Create: `blm/verify.py`, `tests/fixtures/referring_with_link.html`, `tests/fixtures/referring_without_link.html`, `tests/test_verify.py`

**Interfaces:**
- Consumes: `BrokenBacklink`, `MatchResult`
- Produces:
  - `canonical(url: str) -> str` (lower-case host, no scheme, no trailing slash, no fragment)
  - `verify_backlink(bl: BrokenBacklink, client: httpx.Client, timeout: float = 10.0) -> str` returning `"confirmed" | "fixed" | "unknown"`
  - `verify_results(results: list[MatchResult], client, *, sleeper=time.sleep, pause=0.5, progress=None) -> None` (sets `verification` in place; `progress(i, n)` optional callback)

- [ ] **Step 1: Write fixtures**

`tests/fixtures/referring_with_link.html`:
```html
<html><body><p>Wir empfehlen den <a href="https://konkurrent.de/ratgeber/stahl/">Ratgeber</a>.</p></body></html>
```

`tests/fixtures/referring_without_link.html`:
```html
<html><body><p>Wir empfehlen den <a href="https://me.de/stahl">Ratgeber</a>.</p></body></html>
```

- [ ] **Step 2: Write the failing tests**

`tests/test_verify.py`:
```python
from pathlib import Path

import httpx
import respx

from blm.models import BrokenBacklink, MatchResult, RecoveredContent
from blm.verify import canonical, verify_backlink, verify_results

FIX = Path(__file__).parent / "fixtures"
WITH = (FIX / "referring_with_link.html").read_text()
WITHOUT = (FIX / "referring_without_link.html").read_text()
FROM = "https://blog.example/kueche"
DEAD = "https://konkurrent.de/ratgeber/stahl"


def bl():
    return BrokenBacklink(url_from=FROM, url_to=DEAD)


def test_canonical():
    assert canonical("HTTPS://Konkurrent.de/ratgeber/stahl/#x") == "konkurrent.de/ratgeber/stahl"
    assert canonical("http://konkurrent.de/ratgeber/stahl") == canonical(DEAD)


@respx.mock
def test_confirmed_when_404_and_link_present():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, text=WITH))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "confirmed"


@respx.mock
def test_fixed_when_target_alive():
    respx.get(DEAD).mock(return_value=httpx.Response(200, text="ok"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_fixed_when_link_removed():
    respx.get(DEAD).mock(return_value=httpx.Response(410))
    respx.get(FROM).mock(return_value=httpx.Response(200, text=WITHOUT))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "fixed"


@respx.mock
def test_unknown_on_timeout():
    respx.get(DEAD).mock(side_effect=httpx.ConnectTimeout("slow"))
    with httpx.Client() as c:
        assert verify_backlink(bl(), c) == "unknown"


@respx.mock
def test_verify_results_sets_field_and_pauses_between_domains():
    respx.get(DEAD).mock(return_value=httpx.Response(404))
    respx.get(FROM).mock(return_value=httpx.Response(200, text=WITH))
    respx.get("https://other.example/p").mock(return_value=httpx.Response(200, text=WITH))
    rows = [
        MatchResult(bl(), RecoveredContent(DEAD, "t", "wayback")),
        MatchResult(BrokenBacklink(url_from="https://other.example/p", url_to=DEAD), RecoveredContent(DEAD, "t", "wayback")),
    ]
    pauses = []
    seen = []
    with httpx.Client() as c:
        verify_results(rows, c, sleeper=pauses.append, progress=lambda i, n: seen.append((i, n)))
    assert [r.verification for r in rows] == ["confirmed", "confirmed"]
    assert pauses == [0.5]
    assert seen == [(1, 2), (2, 2)]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_verify.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement verify**

`blm/verify.py`:
```python
"""Live checks: is the target still dead, and does the referring page still link to it?"""

from __future__ import annotations

import time
from typing import Callable, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from blm.models import BrokenBacklink, MatchResult
from blm.wayback import USER_AGENT

DEAD_CODES = {404, 410}


def canonical(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def _get(client: httpx.Client, url: str, timeout: float) -> httpx.Response:
    return client.get(url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT})


def _page_links_to(html: str, page_url: str, target: str) -> bool:
    wanted = canonical(target)
    soup = BeautifulSoup(html, "lxml")
    for a in soup.find_all("a", href=True):
        if canonical(urljoin(page_url, a["href"])) == wanted:
            return True
    return False


def verify_backlink(bl: BrokenBacklink, client: httpx.Client, timeout: float = 10.0) -> str:
    try:
        target = _get(client, bl.url_to, timeout)
        if target.status_code not in DEAD_CODES:
            return "fixed"
        source = _get(client, bl.url_from, timeout)
        if source.status_code >= 400:
            return "unknown"
        return "confirmed" if _page_links_to(source.text, bl.url_from, bl.url_to) else "fixed"
    except httpx.HTTPError:
        return "unknown"


def verify_results(
    results: list[MatchResult],
    client: httpx.Client,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    pause: float = 0.5,
    progress: Optional[Callable[[int, int], None]] = None,
) -> None:
    last_host = None
    for i, row in enumerate(results, start=1):
        host = urlparse(row.backlink.url_from).netloc.lower()
        if last_host is not None and host != last_host:
            sleeper(pause)
        row.verification = verify_backlink(row.backlink, client)
        last_host = host
        if progress:
            progress(i, len(results))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_verify.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add blm/verify.py tests/fixtures/referring_with_link.html tests/fixtures/referring_without_link.html tests/test_verify.py
git commit -m "feat: live verification of dead targets and link presence

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Outreach mail draft via chat completion

**Files:**
- Create: `blm/outreach.py`, `tests/test_outreach.py`

**Interfaces:**
- Consumes: `MatchResult`
- Produces:
  - `DEFAULT_CHAT_MODELS = {"openai": "gpt-4.1-mini", "gemini": "gemini-2.5-flash", "ollama": "llama3.1"}`
  - `chat_complete(provider: str, model: str, prompt: str, *, api_key: str | None = None, base_url: str | None = None, client: httpx.Client | None = None) -> str`
  - `build_prompt(row: MatchResult, sender_name: str, own_domain: str, suggestion_title: str = "") -> str`
  - `draft_mail(row, sender_name, own_domain, *, provider, model, api_key=None, base_url=None, client=None, suggestion_title="") -> str`
  - `OutreachError(Exception)`
- Endpoints: OpenAI `POST https://api.openai.com/v1/chat/completions`; Gemini `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=KEY`; Ollama `POST {base_url}/api/chat` with `"stream": false`.

- [ ] **Step 1: Write the failing tests**

`tests/test_outreach.py`:
```python
import httpx
import pytest
import respx

from blm.models import BrokenBacklink, Match, MatchResult, RecoveredContent
from blm.outreach import DEFAULT_CHAT_MODELS, OutreachError, build_prompt, chat_complete, draft_mail

OPENAI = "https://api.openai.com/v1/chat/completions"
GEMINI = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
OLLAMA = "http://localhost:11434/api/chat"


def row():
    bl = BrokenBacklink(url_from="https://blog.example/kueche", url_to="https://konkurrent.de/stahl",
                        anchor="Ratgeber zu Stahlküchen", snippet_left="Wir empfehlen den", snippet_right="von Konkurrent.")
    r = MatchResult(bl, RecoveredContent(bl.url_to, "t", "wayback"))
    r.top = [Match("https://me.de/kueche-aus-stahl", 0.83)]
    return r


def test_defaults_cover_all_providers():
    assert set(DEFAULT_CHAT_MODELS) == {"openai", "gemini", "ollama"}


def test_prompt_contains_all_required_fields():
    p = build_prompt(row(), "Daniel", "me.de", suggestion_title="Küche aus Stahl")
    for needle in ["Daniel", "me.de", "https://blog.example/kueche", "https://konkurrent.de/stahl",
                   "Ratgeber zu Stahlküchen", "Wir empfehlen den", "von Konkurrent.",
                   "https://me.de/kueche-aus-stahl", "Küche aus Stahl", "Deutsch", "120"]:
        assert needle in p


def test_prompt_uses_slug_when_no_title():
    p = build_prompt(row(), "Daniel", "me.de")
    assert "kueche aus stahl" in p


def test_prompt_raises_without_match():
    r = row()
    r.top = []
    with pytest.raises(OutreachError):
        build_prompt(r, "Daniel", "me.de")


@respx.mock
def test_chat_openai():
    respx.post(OPENAI).mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Hallo!"}}]}))
    assert chat_complete("openai", "gpt-4.1-mini", "p", api_key="k") == "Hallo!"


@respx.mock
def test_chat_gemini():
    respx.post(GEMINI).mock(return_value=httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Servus"}]}}]}))
    assert chat_complete("gemini", "gemini-2.5-flash", "p", api_key="k") == "Servus"


@respx.mock
def test_chat_ollama():
    route = respx.post(OLLAMA).mock(return_value=httpx.Response(200, json={"message": {"content": "Moin"}}))
    assert chat_complete("ollama", "llama3.1", "p") == "Moin"
    assert b'"stream": false' in route.calls.last.request.content or b'"stream":false' in route.calls.last.request.content


@respx.mock
def test_chat_error_raises():
    respx.post(OPENAI).mock(return_value=httpx.Response(401, text="nope"))
    with pytest.raises(OutreachError, match="401"):
        chat_complete("openai", "m", "p", api_key="bad")


@respx.mock
def test_draft_mail_end_to_end():
    respx.post(OPENAI).mock(return_value=httpx.Response(200, json={"choices": [{"message": {"content": "Entwurf"}}]}))
    assert draft_mail(row(), "Daniel", "me.de", provider="openai", model="m", api_key="k") == "Entwurf"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_outreach.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement outreach**

`blm/outreach.py`:
```python
"""Draft a short German outreach mail per match using a chat model over HTTP."""

from __future__ import annotations

from typing import Optional

import httpx

from blm.models import MatchResult
from blm.wayback import slug_words

DEFAULT_CHAT_MODELS = {"openai": "gpt-4.1-mini", "gemini": "gemini-2.5-flash", "ollama": "llama3.1"}
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OutreachError(Exception):
    pass


def build_prompt(row: MatchResult, sender_name: str, own_domain: str, suggestion_title: str = "") -> str:
    if not row.top:
        raise OutreachError("Kein Vorschlag vorhanden, Mail-Entwurf nicht möglich.")
    bl = row.backlink
    suggestion = row.top[0].url
    title = suggestion_title or slug_words(suggestion)
    context = " ".join(p for p in (bl.snippet_left, f"[{bl.anchor}]" if bl.anchor else "", bl.snippet_right) if p).strip()
    return (
        "Schreibe eine kurze, freundliche E-Mail auf Deutsch (maximal 120 Wörter, keine Floskeln, "
        "keine Betreffzeile, kein Markdown) an den Betreiber einer Webseite.\n\n"
        f"Absender: {sender_name} von {own_domain}\n"
        f"Seite des Empfängers mit dem Link: {bl.url_from}\n"
        f"Verlinkte, inzwischen tote URL: {bl.url_to}\n"
        f"Ankertext und Kontext des Links: {context or bl.anchor or '(unbekannt)'}\n"
        f"Unsere thematisch passende Seite: {suggestion}\n"
        f"Titel oder Thema unserer Seite: {title}\n\n"
        "Inhalt: Danke für den Artikel, Hinweis dass der verlinkte Beitrag nicht mehr erreichbar ist (404), "
        "kurz erklären was unsere Seite bietet, höflich vorschlagen den Link auf unsere Seite zu setzen. "
        "Keine Übertreibungen, keine Werbesprache. Schließe mit dem Namen des Absenders."
    )


def chat_complete(
    provider: str,
    model: str,
    prompt: str,
    *,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> str:
    own_client = client is None
    client = client or httpx.Client(timeout=90.0)
    try:
        if provider == "openai":
            if not api_key:
                raise OutreachError("openai: API-Schlüssel fehlt")
            resp = client.post(OPENAI_CHAT_URL, headers={"Authorization": f"Bearer {api_key}"},
                               json={"model": model, "messages": [{"role": "user", "content": prompt}]})
            _check(resp, provider)
            return resp.json()["choices"][0]["message"]["content"].strip()
        if provider == "gemini":
            if not api_key:
                raise OutreachError("gemini: API-Schlüssel fehlt")
            resp = client.post(f"{GEMINI_BASE}/{model}:generateContent", params={"key": api_key},
                               json={"contents": [{"parts": [{"text": prompt}]}]})
            _check(resp, provider)
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if provider == "ollama":
            root = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")
            resp = client.post(f"{root}/api/chat", json={"model": model, "stream": False,
                                                         "messages": [{"role": "user", "content": prompt}]})
            _check(resp, provider)
            return resp.json()["message"]["content"].strip()
        raise OutreachError(f"Unbekannter Anbieter: {provider}")
    except httpx.HTTPError as exc:
        raise OutreachError(f"{provider}: {exc}") from exc
    finally:
        if own_client:
            client.close()


def _check(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 400:
        raise OutreachError(f"{provider}: HTTP {resp.status_code}: {resp.text[:300]}")


def draft_mail(
    row: MatchResult,
    sender_name: str,
    own_domain: str,
    *,
    provider: str,
    model: str,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    suggestion_title: str = "",
) -> str:
    prompt = build_prompt(row, sender_name, own_domain, suggestion_title)
    return chat_complete(provider, model, prompt, api_key=api_key, base_url=base_url, client=client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_outreach.py -v`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add blm/outreach.py tests/test_outreach.py
git commit -m "feat: draft outreach mails via chat completion

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 11: Ahrefs API client (optional live fetch)

**Files:**
- Create: `blm/ingest/ahrefs_api.py`, `tests/fixtures/ahrefs_api_response.json`, `tests/test_ahrefs_api.py`

**Interfaces:**
- Consumes: `BrokenBacklink`
- Produces: `fetch_broken_backlinks(token: str, target: str, *, limit: int = 100, include_traffic: bool = False, client: httpx.Client | None = None) -> list[BrokenBacklink]`, `AhrefsError(Exception)`, `AHREFS_URL`

- [ ] **Step 1: Write fixture**

`tests/fixtures/ahrefs_api_response.json`:
```json
{"backlinks": [
  {"url_from": "https://blog.example/kueche", "url_to": "https://konkurrent.de/ratgeber/stahl",
   "anchor": "Ratgeber zu Stahlküchen", "snippet_left": "Wir empfehlen den", "snippet_right": "von Konkurrent.",
   "title": "Beste Küchentipps", "domain_rating_source": 72.0, "url_rating_source": 35.0, "http_code_target": 404},
  {"url_from": "https://forum.example/t/1", "url_to": "https://konkurrent.de/alt",
   "anchor": "hier", "snippet_left": "", "snippet_right": "", "title": "Forum Thread",
   "domain_rating_source": 40.0, "url_rating_source": 10.0, "http_code_target": 404}
]}
```

- [ ] **Step 2: Write the failing tests**

`tests/test_ahrefs_api.py`:
```python
import json
from pathlib import Path

import httpx
import pytest
import respx

from blm.ingest.ahrefs_api import AHREFS_URL, AhrefsError, fetch_broken_backlinks

FIX = Path(__file__).parent / "fixtures"
RESPONSE = json.loads((FIX / "ahrefs_api_response.json").read_text())


@respx.mock
def test_fetch_maps_fields_and_sets_dofollow_content_true():
    route = respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=RESPONSE))
    rows = fetch_broken_backlinks("tok", "konkurrent.de", limit=50)
    assert len(rows) == 2
    assert rows[0].title_from == "Beste Küchentipps"
    assert rows[0].domain_rating == 72.0
    assert rows[0].is_dofollow is True and rows[0].is_content is True
    assert rows[0].page_traffic is None
    req = route.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    p = req.url.params
    assert p["target"] == "konkurrent.de"
    assert p["mode"] == "subdomains"
    assert p["aggregation"] == "1_per_domain"
    assert p["order_by"] == "domain_rating_source:desc"
    assert p["limit"] == "50"
    assert "traffic" not in p["select"].split(",")
    where = json.loads(p["where"])
    assert {"field": "is_dofollow", "is": ["eq", True]} in where["and"]
    assert {"field": "is_content", "is": ["eq", True]} in where["and"]


@respx.mock
def test_fetch_with_traffic():
    resp = {"backlinks": [dict(RESPONSE["backlinks"][0], traffic=1200)]}
    route = respx.get(AHREFS_URL).mock(return_value=httpx.Response(200, json=resp))
    rows = fetch_broken_backlinks("tok", "konkurrent.de", include_traffic=True)
    assert rows[0].page_traffic == 1200
    assert "traffic" in route.calls.last.request.url.params["select"].split(",")


@respx.mock
def test_api_error_is_readable():
    respx.get(AHREFS_URL).mock(return_value=httpx.Response(403, json={"error": "Insufficient units"}))
    with pytest.raises(AhrefsError, match="403"):
        fetch_broken_backlinks("tok", "konkurrent.de")


def test_missing_token():
    with pytest.raises(AhrefsError):
        fetch_broken_backlinks("", "konkurrent.de")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_ahrefs_api.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 4: Implement the client**

`blm/ingest/ahrefs_api.py`:
```python
"""Optional live fetch of broken backlinks from the Ahrefs API v3.

Costs API units per row; `traffic` costs 10 extra units per row and is only
requested when include_traffic is True.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

from blm.models import BrokenBacklink

AHREFS_URL = "https://api.ahrefs.com/v3/site-explorer/broken-backlinks"
BASE_SELECT = [
    "url_from", "url_to", "anchor", "snippet_left", "snippet_right", "title",
    "domain_rating_source", "url_rating_source", "http_code_target",
]


class AhrefsError(Exception):
    pass


def fetch_broken_backlinks(
    token: str,
    target: str,
    *,
    limit: int = 100,
    include_traffic: bool = False,
    client: Optional[httpx.Client] = None,
) -> list[BrokenBacklink]:
    if not token:
        raise AhrefsError("Ahrefs-API-Schlüssel fehlt.")
    select = BASE_SELECT + (["traffic"] if include_traffic else [])
    params = {
        "target": target,
        "mode": "subdomains",
        "aggregation": "1_per_domain",
        "where": json.dumps({"and": [
            {"field": "is_dofollow", "is": ["eq", True]},
            {"field": "is_content", "is": ["eq", True]},
        ]}),
        "order_by": "domain_rating_source:desc",
        "select": ",".join(select),
        "limit": str(limit),
        "output": "json",
    }
    own_client = client is None
    client = client or httpx.Client(timeout=60.0)
    try:
        resp = client.get(AHREFS_URL, params=params, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise AhrefsError(f"Ahrefs-Anfrage fehlgeschlagen: {exc}") from exc
    finally:
        if own_client:
            client.close()
    if resp.status_code >= 400:
        raise AhrefsError(f"Ahrefs API HTTP {resp.status_code}: {resp.text[:300]}")

    rows = []
    for item in resp.json().get("backlinks", []):
        rows.append(BrokenBacklink(
            url_from=item["url_from"],
            url_to=item["url_to"],
            anchor=item.get("anchor") or "",
            snippet_left=item.get("snippet_left") or "",
            snippet_right=item.get("snippet_right") or "",
            title_from=item.get("title") or "",
            domain_rating=item.get("domain_rating_source"),
            url_rating=item.get("url_rating_source"),
            page_traffic=item.get("traffic"),
            is_dofollow=True,
            is_content=True,
            http_code_target=item.get("http_code_target"),
        ))
    return rows
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_ahrefs_api.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add blm/ingest/ahrefs_api.py tests/fixtures/ahrefs_api_response.json tests/test_ahrefs_api.py
git commit -m "feat: optional Ahrefs API v3 client for broken backlinks

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 12: Export (DataFrame, CSV, XLSX)

**Files:**
- Create: `blm/export.py`, `tests/test_export.py`

**Interfaces:**
- Consumes: `MatchResult`
- Produces: `results_to_dataframe(results: list[MatchResult]) -> pd.DataFrame` with German column names in this order: `Priorität, Rang Linkwert, Linkgebende URL, DR, UR, Traffic, Anker, Tote URL, Quelle Text, Snapshot, Vorschlag 1, Score 1, Vorschlag 2, Score 2, Vorschlag 3, Score 3, Content-Gap, Verifikation, Fehler`; `to_csv_bytes(df) -> bytes` (UTF-8 with BOM, semicolon separated for German Excel); `to_xlsx_bytes(df) -> bytes`; `format_snapshot(ts: str | None) -> str` turning `20240315120000` into `2024-03-15`.

- [ ] **Step 1: Write the failing tests**

`tests/test_export.py`:
```python
import io

import pandas as pd

from blm.export import format_snapshot, results_to_dataframe, to_csv_bytes, to_xlsx_bytes
from blm.models import BrokenBacklink, Match, MatchResult, RecoveredContent


def rows():
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="Anker", domain_rating=55.0, value_rank=1)
    r = MatchResult(bl, RecoveredContent(bl.url_to, "t", "wayback", snapshot_timestamp="20240315120000"), value_rank=1, priority=1)
    r.top = [Match("https://me.de/1", 0.91), Match("https://me.de/2", 0.7)]
    r.verification = "confirmed"
    gap = MatchResult(BrokenBacklink(url_from="https://b.de", url_to="https://c.de/y", value_rank=2),
                      RecoveredContent("https://c.de/y", "t", "fallback", error="Kein Snapshot mit Status 200"),
                      is_content_gap=True, value_rank=2, priority=2)
    gap.errors = ["Kein Snapshot mit Status 200"]
    return [r, gap]


def test_format_snapshot():
    assert format_snapshot("20240315120000") == "2024-03-15"
    assert format_snapshot(None) == ""


def test_dataframe_columns_and_values():
    df = results_to_dataframe(rows())
    assert list(df.columns)[:4] == ["Priorität", "Rang Linkwert", "Linkgebende URL", "DR"]
    assert df.loc[0, "Vorschlag 1"] == "https://me.de/1"
    assert df.loc[0, "Score 1"] == 0.91
    assert df.loc[0, "Vorschlag 3"] == ""
    assert df.loc[0, "Snapshot"] == "2024-03-15"
    assert df.loc[1, "Quelle Text"] == "fallback"
    assert bool(df.loc[1, "Content-Gap"]) is True
    assert "Kein Snapshot" in df.loc[1, "Fehler"]


def test_csv_bytes_use_bom_and_semicolon():
    data = to_csv_bytes(results_to_dataframe(rows()))
    assert data.startswith("﻿".encode("utf-8"))
    assert b"Priorit" in data and b";" in data


def test_xlsx_roundtrip():
    data = to_xlsx_bytes(results_to_dataframe(rows()))
    back = pd.read_excel(io.BytesIO(data))
    assert len(back) == 2
    assert back.loc[0, "Linkgebende URL"] == "https://a.de/p"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_export.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement export**

`blm/export.py`:
```python
"""Turn MatchResult rows into a DataFrame and downloadable files."""

from __future__ import annotations

import io
from typing import Optional

import pandas as pd

from blm.models import MatchResult

COLUMNS = [
    "Priorität", "Rang Linkwert", "Linkgebende URL", "DR", "UR", "Traffic", "Anker", "Tote URL",
    "Quelle Text", "Snapshot", "Vorschlag 1", "Score 1", "Vorschlag 2", "Score 2", "Vorschlag 3", "Score 3",
    "Content-Gap", "Verifikation", "Fehler",
]


def format_snapshot(ts: Optional[str]) -> str:
    if not ts or len(ts) < 8:
        return ""
    return f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"


def results_to_dataframe(results: list[MatchResult]) -> pd.DataFrame:
    records = []
    for r in results:
        top = r.top + [None] * (3 - len(r.top))
        rec = {
            "Priorität": r.priority,
            "Rang Linkwert": r.value_rank,
            "Linkgebende URL": r.backlink.url_from,
            "DR": r.backlink.domain_rating,
            "UR": r.backlink.url_rating,
            "Traffic": r.backlink.page_traffic,
            "Anker": r.backlink.anchor,
            "Tote URL": r.backlink.url_to,
            "Quelle Text": r.recovered.source,
            "Snapshot": format_snapshot(r.recovered.snapshot_timestamp),
        }
        for i, m in enumerate(top, start=1):
            rec[f"Vorschlag {i}"] = m.url if m else ""
            rec[f"Score {i}"] = round(m.score, 3) if m else None
        rec["Content-Gap"] = r.is_content_gap
        rec["Verifikation"] = r.verification
        rec["Fehler"] = " | ".join(r.errors)
        records.append(rec)
    return pd.DataFrame.from_records(records, columns=COLUMNS)


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";").encode("utf-8-sig")


def to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Treffer")
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_export.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add blm/export.py tests/test_export.py
git commit -m "feat: export results as DataFrame, CSV and XLSX

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 13: Embedding cache helper

**Files:**
- Modify: `blm/embeddings/__init__.py` (add `embed_cached`)
- Modify: `tests/test_embeddings.py` (append tests)

**Interfaces:**
- Consumes: `EmbeddingProvider`, `JsonCache`
- Produces: `embed_cached(provider: EmbeddingProvider, texts: list[str], cache: JsonCache | None) -> list[np.ndarray | None]`. Cache namespace `"embeddings"`, key `f"{provider.name}|{provider.model}|{text}"`. Only texts without a cache hit are sent to the provider; successful results are written back.

- [ ] **Step 1: Append the failing tests**

Append to `tests/test_embeddings.py`:
```python
from blm.cache import JsonCache
from blm.embeddings import embed_cached


@respx.mock
def test_embed_cached_only_requests_misses_and_writes_back(tmp_path):
    import json

    seen = []

    def handler(request):
        inputs = json.loads(request.content)["input"]
        seen.append(inputs)
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [float(len(t))]} for i, t in enumerate(inputs)]})

    respx.post(OPENAI_URL).mock(side_effect=handler)
    cache = JsonCache(tmp_path)
    p = make_provider("openai", "m", api_key="k")
    first = embed_cached(p, ["aa", "bbb"], cache)
    assert [v.tolist() for v in first] == [[2.0], [3.0]]
    second = embed_cached(p, ["aa", "cccc"], cache)
    assert [v.tolist() for v in second] == [[2.0], [4.0]]
    assert seen == [["aa", "bbb"], ["cccc"]]


@respx.mock
def test_embed_cached_key_includes_model(tmp_path):
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]}))
    cache = JsonCache(tmp_path)
    embed_cached(make_provider("openai", "m1", api_key="k"), ["x"], cache)
    assert cache.get("embeddings", "openai|m1|x") == {"v": [1.0]}
    assert cache.get("embeddings", "openai|m2|x") is None


def test_embed_cached_without_cache_calls_provider():
    class Fake(EmbeddingProvider):
        name = "fake"

        def _embed_batch(self, texts):
            return [[1.0] for _ in texts]

    out = embed_cached(Fake("m"), ["a", "b"], None)
    assert len(out) == 2 and out[0].tolist() == [1.0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_embeddings.py -v -k cached`
Expected: FAIL with `ImportError: cannot import name 'embed_cached'`

- [ ] **Step 3: Implement**

Add to `blm/embeddings/__init__.py` (below `make_provider`, and add `"embed_cached"` to `__all__`):
```python
import numpy as np

from blm.cache import JsonCache


def embed_cached(provider: EmbeddingProvider, texts: list[str], cache: Optional[JsonCache]) -> list[Optional[np.ndarray]]:
    """Embed texts, reusing cached vectors keyed by provider, model and text."""
    vectors: list[Optional[np.ndarray]] = [None] * len(texts)
    todo: list[int] = []
    for i, text in enumerate(texts):
        hit = cache.get("embeddings", f"{provider.name}|{provider.model}|{text}") if cache else None
        if hit is not None:
            vectors[i] = np.asarray(hit["v"], dtype=np.float32)
        else:
            todo.append(i)
    if todo:
        fresh = provider.embed([texts[i] for i in todo])
        for i, vec in zip(todo, fresh):
            vectors[i] = vec
            if vec is not None and cache is not None:
                cache.set("embeddings", f"{provider.name}|{provider.model}|{texts[i]}", {"v": vec.tolist()})
    return vectors
```
Move the `import numpy as np` and `from blm.cache import JsonCache` lines to the top import block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_embeddings.py -v`
Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add blm/embeddings/__init__.py tests/test_embeddings.py
git commit -m "feat: cache embeddings on disk keyed by provider, model and text

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 14: Streamlit app

**Files:**
- Create: `app.py`, `tests/test_app.py`

**Interfaces:**
- Consumes everything above. Session-state keys used: `frog` (FrogImport), `frog_name`, `dim_ok`, `probe_dim`, `bl_df`, `bl_name`, `bl_mapping`, `raw_backlinks`, `ranked`, `recovered_for`, `recovered`, `vectors`, `results`, `results_params`, `draft_<priority>`.
- The smoke test seeds session state so all five sections render without network.

- [ ] **Step 1: Write the failing smoke test**

`tests/test_app.py`:
```python
import numpy as np
from streamlit.testing.v1 import AppTest

from blm.ingest.frog_csv import FrogImport
from blm.models import BrokenBacklink, OwnPage, RecoveredContent


def test_app_renders_sidebar_and_first_sections():
    at = AppTest.from_file("app.py", default_timeout=30).run()
    assert not at.exception
    headers = [h.value for h in at.header]
    assert any(h.startswith("1.") for h in headers)
    assert any(h.startswith("2.") for h in headers)
    assert at.sidebar.selectbox[0].value == "openai"


def test_app_renders_all_five_sections_with_seeded_state():
    at = AppTest.from_file("app.py", default_timeout=30)
    pages = [OwnPage("https://me.de/a", np.array([1.0, 0.0], dtype=np.float32), title="Seite A"),
             OwnPage("https://me.de/b", np.array([0.0, 1.0], dtype=np.float32))]
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="x", domain_rating=50.0)
    at.session_state["frog"] = FrogImport(pages=pages, dimension=2, skipped=0)
    at.session_state["frog_name"] = "frog.csv"
    at.session_state["dim_ok"] = True
    at.session_state["probe_dim"] = 2
    at.session_state["raw_backlinks"] = [bl]
    at.session_state["recovered_for"] = [BrokenBacklink(**{**bl.__dict__, "value_rank": 1})]
    at.session_state["recovered"] = [RecoveredContent("https://c.de/x", "text", "wayback", "20240101000000")]
    at.session_state["vectors"] = [np.array([1.0, 0.0], dtype=np.float32)]
    at.run()
    assert not at.exception
    numbers = sorted(h.value[0] for h in at.header if h.value[0].isdigit())
    assert numbers == ["1", "2", "3", "4", "5"]
    assert len(at.session_state["results"]) == 1
    assert at.session_state["results"][0].top[0].url == "https://me.de/a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: FAIL (app.py missing)

- [ ] **Step 3: Write app.py**

`app.py`:
```python
"""Broken Link Matcher: Streamlit UI. Wiring only; all logic lives in blm/."""

from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pandas as pd
import streamlit as st

from blm.cache import JsonCache
from blm.embeddings import DEFAULT_EMBED_MODELS, PROVIDERS, EmbeddingError, embed_cached, make_provider
from blm.export import results_to_dataframe, to_csv_bytes, to_xlsx_bytes
from blm.ingest.ahrefs_api import AhrefsError, fetch_broken_backlinks
from blm.ingest.backlinks_csv import OPTIONAL_FIELDS, REQUIRED_FIELDS, detect_columns, parse_backlinks, read_table
from blm.ingest.frog_csv import load_frog_embeddings
from blm.matcher import build_results
from blm.outreach import DEFAULT_CHAT_MODELS, OutreachError, draft_mail
from blm.ranking import SORT_FIELDS, rank_backlinks
from blm.verify import verify_results
from blm.wayback import recover_content

st.set_page_config(page_title="Broken Link Matcher", page_icon="🔗", layout="wide")
S = st.session_state
CACHE = JsonCache(Path(__file__).parent / ".cache")
SORT_LABELS = {"domain_rating": "Domain Rating", "url_rating": "URL Rating", "page_traffic": "Seitentraffic"}


def secret(name: str) -> str:
    """Env var or st.secrets fallback for a key; never persisted by the app."""
    value = os.environ.get(name.upper(), "")
    if value:
        return value
    try:
        return str(st.secrets.get(name.upper(), ""))
    except Exception:  # no secrets file or key: fall through to empty
        return ""


# ----------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Einstellungen")
    provider = st.selectbox("Embedding-Anbieter (wie im Screaming Frog)", PROVIDERS)
    embed_model = st.text_input("Embedding-Modell (exakt wie im Frog)", value=DEFAULT_EMBED_MODELS[provider])
    if provider == "ollama":
        base_url = st.text_input("Ollama-URL", value="http://localhost:11434")
        api_key = None
    else:
        base_url = None
        api_key = st.text_input(f"{provider.capitalize()} API-Schlüssel", type="password", value=secret(f"{provider}_api_key"))
    chat_model = st.text_input("Chat-Modell für Mail-Entwürfe", value=DEFAULT_CHAT_MODELS[provider])
    st.divider()
    ahrefs_key = st.text_input("Ahrefs-API-Schlüssel (optional)", type="password", value=secret("ahrefs_api_key"))
    st.divider()
    sender_name = st.text_input("Dein Name (für Mail-Entwürfe)")
    own_domain = st.text_input("Deine Domain (für Mail-Entwürfe)")
    st.divider()
    if st.button("Cache leeren"):
        st.success(f"{CACHE.clear()} Einträge gelöscht")
    st.caption("Schlüssel bleiben in dieser Sitzung und werden nicht gespeichert.")


def provider_or_error():
    try:
        return make_provider(provider, embed_model, api_key=api_key, base_url=base_url)
    except EmbeddingError as exc:
        st.error(str(exc))
        return None


st.title("Broken Link Matcher")
st.caption("Broken Link Building mit semantischem Matching: tote Wettbewerber-URLs, Wayback-Inhalt, Embeddings, deine passendste Seite.")

# ----------------------------------------------------------------- 1. own domain
st.header("1. Eigene Domain (Screaming-Frog-Embeddings)")
frog_file = st.file_uploader("Embeddings-Export aus dem Screaming Frog (CSV)", type=["csv"], key="frog_upload")
if frog_file is not None and S.get("frog_name") != frog_file.name:
    try:
        S["frog"] = load_frog_embeddings(frog_file)
        S["frog_name"] = frog_file.name
        S.pop("dim_ok", None)
        S.pop("probe_dim", None)
    except ValueError as exc:
        st.error(str(exc))
if "frog" in S:
    imp = S["frog"]
    st.write(f"{len(imp.pages)} URLs, Vektordimension {imp.dimension}, {imp.skipped} Zeilen übersprungen.")
    if st.button("Dimensionscheck gegen gewähltes Modell"):
        prov = provider_or_error()
        if prov is not None:
            try:
                S["probe_dim"] = prov.probe_dimension()
                S["dim_ok"] = S["probe_dim"] == imp.dimension
            except EmbeddingError as exc:
                st.error(str(exc))
    if "probe_dim" in S:
        if S.get("dim_ok"):
            st.success(f"Dimension passt ({S['probe_dim']}).")
        else:
            st.error(f"Dimension passt nicht: Frog-CSV {imp.dimension}, Modell {S['probe_dim']}. Wähle exakt das Modell, das im Frog konfiguriert ist.")

# ----------------------------------------------------------------- 2. backlinks
st.header("2. Wettbewerber-Backlinks")
tab_csv, tab_api = st.tabs(["CSV/XLSX-Upload", "Ahrefs-API"])
with tab_csv:
    bl_file = st.file_uploader("Broken-Backlinks-Export (Ahrefs oder anderes Tool)", type=["csv", "xlsx"], key="bl_upload")
    if bl_file is not None and S.get("bl_name") != bl_file.name:
        try:
            S["bl_df"] = read_table(bl_file, filename=bl_file.name)
            S["bl_name"] = bl_file.name
            S["bl_mapping"] = detect_columns(S["bl_df"])
        except Exception as exc:  # pandas raises many types for malformed files
            st.error(f"Datei konnte nicht gelesen werden: {exc}")
    if "bl_df" in S:
        cm = S["bl_mapping"]
        mapping = dict(cm.mapping)
        if cm.missing:
            st.warning("Pflichtspalten nicht erkannt. Bitte zuordnen.")
        if cm.missing or st.checkbox("Spaltenzuordnung anpassen"):
            options = ["(keine)"] + cm.columns
            for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
                current = mapping.get(field, "(keine)")
                choice = st.selectbox(field, options, index=options.index(current) if current in options else 0, key=f"map_{field}")
                if choice == "(keine)":
                    mapping.pop(field, None)
                else:
                    mapping[field] = choice
        if st.button("Backlinks übernehmen"):
            try:
                S["raw_backlinks"] = parse_backlinks(S["bl_df"], mapping)
                st.success(f"{len(S['raw_backlinks'])} Backlinks übernommen.")
            except ValueError as exc:
                st.error(str(exc))
with tab_api:
    target = st.text_input("Wettbewerber-Domain", placeholder="konkurrent.de")
    api_limit = st.number_input("Maximale Zeilen", min_value=10, max_value=1000, value=100, step=10)
    include_traffic = st.checkbox("Seitentraffic mitladen (10 API-Units extra pro Zeile)")
    if not ahrefs_key:
        st.caption("Ohne Ahrefs-API-Schlüssel steht nur der CSV-Weg zur Verfügung.")
    if st.button("Von Ahrefs abrufen", disabled=not (ahrefs_key and target)):
        try:
            S["raw_backlinks"] = fetch_broken_backlinks(ahrefs_key, target, limit=int(api_limit), include_traffic=include_traffic)
            st.success(f"{len(S['raw_backlinks'])} Backlinks geladen.")
        except AhrefsError as exc:
            st.error(f"{exc} Alternative: CSV-Export aus Ahrefs hochladen.")

if "raw_backlinks" in S:
    c1, c2, c3, c4, c5 = st.columns(5)
    dofollow_only = c1.checkbox("Nur Dofollow", value=True)
    content_only = c2.checkbox("Nur Content-Links", value=True)
    min_dr = c3.slider("Mindest-DR", 0, 100, 0)
    sort_by = c4.selectbox("Sortieren nach", SORT_FIELDS, format_func=SORT_LABELS.get)
    limit = c5.number_input("Obergrenze", min_value=1, max_value=1000, value=100)
    S["ranked"] = rank_backlinks(S["raw_backlinks"], dofollow_only=dofollow_only, content_only=content_only, min_dr=float(min_dr), sort_by=sort_by, limit=int(limit))
    preview = pd.DataFrame([{"Rang": b.value_rank, "Linkgebende URL": b.url_from, "DR": b.domain_rating, "UR": b.url_rating,
                             "Traffic": b.page_traffic, "Anker": b.anchor, "Tote URL": b.url_to} for b in S["ranked"]])
    st.dataframe(preview, use_container_width=True, hide_index=True)

# ----------------------------------------------------------------- 3. wayback
if "ranked" in S:
    st.header("3. Wayback-Abruf")
    max_chars = st.number_input("Maximale Zeichen pro Text", min_value=1000, max_value=50000, value=12000, step=1000)
    st.caption("Immer der jüngste Snapshot mit Status 200. Ohne Snapshot: Fallback aus Anker, Kontext, Titel und URL-Pfad, kein generierter Text.")
    if st.button("Inhalte aus der Wayback Machine holen"):
        ranked = S["ranked"]
        recovered = []
        bar = st.progress(0.0, text="Starte …")
        with httpx.Client() as client:
            for i, bl in enumerate(ranked, start=1):
                recovered.append(recover_content(bl, client, CACHE, max_chars=int(max_chars)))
                bar.progress(i / len(ranked), text=f"{i}/{len(ranked)}: {bl.url_to}")
                if i < len(ranked):
                    time.sleep(1.0)
        S["recovered_for"] = ranked
        S["recovered"] = recovered
        for key in ("vectors", "results", "results_params"):
            S.pop(key, None)
    if "recovered" in S:
        rec = S["recovered"]
        counts = {src: sum(r.source == src for r in rec) for src in ("wayback", "fallback", "none")}
        st.write(f"Snapshots: {counts['wayback']} · Fallback aus Ahrefs-Feldern: {counts['fallback']} · Kein Text: {counts['none']}")
        with st.expander("Rekonstruierte Texte ansehen"):
            for r in rec:
                label = f"**{r.url_to}** · {r.source}" + (f" · Snapshot {r.snapshot_timestamp[:8]}" if r.snapshot_timestamp else "")
                st.markdown(label)
                st.text((r.text or "(kein Text)")[:600])

# ----------------------------------------------------------------- 4. matching
if "recovered" in S:
    st.header("4. Matching")
    threshold = st.slider("Schwellwert: darunter gilt eine Zeile als Content-Gap", 0.0, 1.0, 0.5, 0.01)
    match_fallback = st.checkbox("Fallback-Zeilen (ohne Snapshot) ebenfalls matchen", value=True)
    blocked = "frog" not in S or S.get("dim_ok") is not True
    if blocked:
        st.warning("Erst die Frog-CSV laden und den Dimensionscheck bestehen.")
    if st.button("Matching starten", disabled=blocked):
        prov = provider_or_error()
        if prov is not None:
            texts = [r.text for r in S["recovered"]]
            idx = [i for i, t in enumerate(texts) if t]
            try:
                with st.spinner("Embeddings werden berechnet …"):
                    fresh = embed_cached(prov, [texts[i] for i in idx], CACHE)
                vectors = [None] * len(texts)
                for j, i in enumerate(idx):
                    vectors[i] = fresh[j]
                S["vectors"] = vectors
                S.pop("results_params", None)
            except EmbeddingError as exc:
                st.error(str(exc))
    if "vectors" in S:
        params = (threshold, match_fallback)
        if S.get("results_params") != params:
            S["results"] = build_results(S["recovered_for"], S["recovered"], S["vectors"], S["frog"].pages,
                                         threshold=threshold, match_fallback=match_fallback)
            S["results_params"] = params
        df = results_to_dataframe(S["results"])
        only_gaps = st.checkbox("Nur Content-Gaps zeigen")
        shown = df[df["Content-Gap"]] if only_gaps else df
        st.dataframe(shown.style.apply(lambda row: ["background-color: #ffe5e5" if row["Content-Gap"] else ""] * len(row), axis=1),
                     use_container_width=True, hide_index=True)

# ----------------------------------------------------------------- 5. verify + outreach
if "results" in S:
    st.header("5. Verifikation und Outreach")
    if st.button("Live prüfen: Ziel noch 404 und Link noch vorhanden?"):
        bar = st.progress(0.0)
        with httpx.Client() as client:
            verify_results(S["results"], client, progress=lambda i, n: bar.progress(i / n, text=f"{i}/{n}"))
        st.success("Verifikation abgeschlossen.")
    df = results_to_dataframe(S["results"])
    c1, c2 = st.columns(2)
    c1.download_button("CSV herunterladen", to_csv_bytes(df), "broken-link-matches.csv", "text/csv")
    c2.download_button("Excel herunterladen", to_xlsx_bytes(df), "broken-link-matches.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.subheader("Mail-Entwürfe")
    titles = {p.url: p.title for p in S["frog"].pages}
    for r in S["results"]:
        if not r.top:
            continue
        dr = f"DR {r.backlink.domain_rating:.0f}" if r.backlink.domain_rating is not None else "DR unbekannt"
        with st.expander(f"#{r.priority} · {dr} · {r.backlink.url_from}"):
            st.write(f"Tote URL: {r.backlink.url_to}")
            st.write(f"Vorschlag: {r.top[0].url} (Score {r.top[0].score:.2f}) · Verifikation: {r.verification}")
            if st.button("Mail-Entwurf erzeugen", key=f"mail_{r.priority}"):
                try:
                    S[f"draft_{r.priority}"] = draft_mail(
                        r, sender_name or "Ich", own_domain or "unserer Seite",
                        provider=provider, model=chat_model, api_key=api_key, base_url=base_url,
                        suggestion_title=titles.get(r.top[0].url, ""),
                    )
                except OutreachError as exc:
                    st.error(str(exc))
            if f"draft_{r.priority}" in S:
                st.text_area("Entwurf (editierbar)", S[f"draft_{r.priority}"], height=220, key=f"ta_{r.priority}")
```

- [ ] **Step 4: Run the smoke tests**

Run: `.venv/bin/pytest tests/test_app.py -v`
Expected: 2 passed. If `at.header` values differ in structure, print `[h.value for h in at.header]` once to adjust the assertion; if `st.dataframe(...style...)` raises inside AppTest, replace the styled call with a plain `st.dataframe(shown, ...)` and keep the "Nur Content-Gaps" filter as the highlight mechanism.

- [ ] **Step 5: Run the whole suite and start the app once**

Run: `.venv/bin/pytest -q`
Expected: all tests pass.

Run: `.venv/bin/streamlit run app.py --server.headless true --server.port 8501` in the background, open `http://localhost:8501`, confirm the sidebar and sections 1 and 2 render, then stop it.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: Streamlit UI wiring the five-step workflow

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 15: README, secrets template, and real-export verification

**Files:**
- Create: `README.md`, `.streamlit/secrets.example.toml`
- Possibly modify: `blm/ingest/backlinks_csv.py` (FIELD_ALIASES) after checking a real Ahrefs UI export

- [ ] **Step 1: Write the secrets template**

`.streamlit/secrets.example.toml`:
```toml
# Copy to .streamlit/secrets.toml (gitignored) or set the same names as environment variables.
OPENAI_API_KEY = ""
GEMINI_API_KEY = ""
AHREFS_API_KEY = ""
```

- [ ] **Step 2: Write the README**

`README.md` (German with an English summary at the end). Sections and required content:

```markdown
# Broken Link Matcher

Broken Link Building mit semantischem Matching. Das Tool nimmt die Broken Backlinks eines Wettbewerbers, holt den Inhalt der toten Seiten aus der Wayback Machine, embeddet ihn und findet per Kosinus-Ähnlichkeit die drei passendsten Seiten deiner Domain. Pro Treffer entsteht ein Mail-Entwurf an den Linkgeber. Tote Seiten ohne passendes Pendant werden als Content-Gap markiert.

Vorgestellt auf der SEOKomm 2026.

## Ablauf

1. Eigene Domain: Screaming-Frog-Crawl mit Embeddings, Export hochladen, Dimensionscheck.
2. Wettbewerber-Backlinks: Ahrefs-Export hochladen (oder per API laden), filtern, nach Linkwert sortieren.
3. Wayback-Abruf: jüngster Snapshot mit Status 200 pro toter URL, Haupttext-Extraktion. Ohne Snapshot: Fallback aus Anker, Kontext, Titel und URL-Pfad. Es wird nie Text generiert.
4. Matching: Embeddings mit demselben Modell wie im Frog, Top 3 pro URL, Content-Gap unter dem Schwellwert.
5. Verifikation und Outreach: Live-Check (Ziel noch 404? Link noch da?), Export als CSV/Excel, Mail-Entwurf pro Treffer.

## Installation

Mit uv (empfohlen, holt Python 3.11 selbst):

    uv python install 3.11
    uv venv --python 3.11 .venv
    source .venv/bin/activate
    uv pip install -r requirements.txt
    streamlit run app.py

Mit vorhandenem Python 3.11+:

    python3.11 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    streamlit run app.py

## Screaming Frog vorbereiten

- Configuration → API Access → (OpenAI | Gemini | Ollama): Schlüssel eintragen, Embedding-Modell wählen.
- Configuration → Custom → Custom JavaScript: Snippet "Extract embeddings from page content" aktivieren (oder das Embeddings-Feature deiner Frog-Version).
- Crawlen, dann Bulk Export → Embeddings (CSV). Die Datei hat eine Spalte `url` und danach `embedding_0 … embedding_N`.
- Merke dir Anbieter und Modellnamen; im Tool musst du exakt dieselben wählen. Der Dimensionscheck fängt Abweichungen ab.

## Ahrefs-Daten

- Site Explorer → Wettbewerber-Domain → Backlinks → Broken. Filter Dofollow setzen, nach DR sortieren, Export CSV.
- Alternativ Ahrefs-API v3 (planabhängig): Schlüssel in der Seitenleiste eintragen. Jede Zeile kostet API-Units; Seitentraffic kostet 10 Units extra pro Zeile und ist deshalb optional.
- Andere Tools: Export hochladen, Spalten manuell zuordnen.

## Schlüssel

Über die Seitenleiste, Umgebungsvariablen (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `AHREFS_API_KEY`) oder `.streamlit/secrets.toml` (siehe `secrets.example.toml`). Schlüssel werden nie auf Platte geschrieben.

## Kosten und Etikette

- Wayback Machine: eine Anfrage pro Sekunde, Wiederholungen mit Backoff. Bitte nicht parallelisieren.
- Embeddings: pro toter URL ein Text von maximal 12000 Zeichen. Ergebnisse werden in `.cache/` gespeichert.
- Schwellwert: 0,5 ist ein Startwert. Die Score-Verteilung hängt vom Modell ab; an eigenen Daten kalibrieren.

## Deployment auf Streamlit Community Cloud

Repo verbinden, `app.py` als Einstieg, Schlüssel unter App Settings → Secrets im TOML-Format hinterlegen. Der Cache ist dort flüchtig.

## Tests

    pytest -q

Kein Netzwerk in Tests; HTTP wird mit respx gemockt.

## English summary

Broken link building with semantic matching: pull a competitor's broken backlinks (Ahrefs export or API), recover the dead pages from the Wayback Machine (newest 200 snapshot, raw HTML via `id_`), embed with the same model your Screaming Frog used for your own site, rank your top 3 matching URLs by cosine similarity, flag content gaps, verify live, export, and draft outreach mails. Python 3.11+, Streamlit, no provider SDKs, fully mocked tests.
```

- [ ] **Step 3: Verify the Ahrefs UI export aliases against a real file**

Ask the user for one real Broken Backlinks CSV exported from the Ahrefs UI (any competitor, a handful of rows is enough). Run:

```bash
.venv/bin/python -c "
from blm.ingest.backlinks_csv import read_table, detect_columns
df = read_table('PATH_TO_REAL_EXPORT.csv')
cm = detect_columns(df)
print('columns:', cm.columns)
print('mapping:', cm.mapping)
print('missing:', cm.missing)
"
```

If any of `url_from`, `url_to`, `anchor`, `domain_rating`, `is_nofollow`/`is_dofollow`, `is_content`, `title_from`, `snippet_left`, `snippet_right`, `page_traffic`, `http_code_target` is not mapped, add the real column name (lower-cased) to `FIELD_ALIASES` in `blm/ingest/backlinks_csv.py` and add the real header line to `tests/fixtures/ahrefs_ui_export.csv` (keep the two data rows, adjust column order). Re-run `.venv/bin/pytest tests/test_backlinks_csv.py -q`. If no real export is available, leave a note in the README under "Ahrefs-Daten": "Spaltennamen des UI-Exports wurden gegen Ahrefs-Stand 2026 geprüft" only once verified; otherwise write "Falls Spalten nicht erkannt werden, per Zuordnungsmaske zuweisen und gerne ein Issue mit den Spaltennamen eröffnen."

- [ ] **Step 4: Final full run**

Run: `.venv/bin/pytest -q`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md .streamlit/secrets.example.toml blm/ingest/backlinks_csv.py tests/fixtures/ahrefs_ui_export.csv
git commit -m "docs: README, secrets template, verify Ahrefs export aliases

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes (spec coverage)

| Spec section | Task |
|---|---|
| 2.1 Data model | 1 |
| frog_csv | 2 |
| backlinks_csv incl. mapping UI | 3, 14 |
| ahrefs_api | 11 |
| ranking with min DR, sort choice, value_rank | 4 |
| wayback newest 200, id_, trafilatura, fallback from fields only, retries | 6 |
| embeddings three providers, probe_dimension, split on error | 7 |
| embeddings cache | 13 |
| matcher top 3, threshold, fallback toggle, priority | 8 |
| verify | 9 |
| outreach | 10 |
| cache | 5 |
| export CSV/XLSX | 12 |
| Streamlit five sections, secrets handling, progress, cache clear | 14 |
| README, deployment, secrets template | 15 |
| Tests without network | every task; respx |
