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
    # one pause between CDX query and snapshot fetch (inside recover_content) plus one pause after
    # the uncached URL; the fallback row (last URL) makes no fetch and no pause
    assert sleeps == [1.0, 1.0]
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
    # only the dimension probe hits the provider; every text embedding comes from the cache
    assert [c for c in provider.calls if c != ["Dimensionstest"]] == []


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
