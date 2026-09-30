import hashlib
import time
from pathlib import Path

import numpy as np
from streamlit.testing.v1 import AppTest

from blm.ingest.frog_csv import FrogImport
from blm.models import BrokenBacklink, OwnPage, RecoveredContent

APP = str(Path(__file__).resolve().parent.parent / "app.py")
MODEL_SETTINGS = ("openai", "text-embedding-3-small", None)


def seeded_app(backlinks=None, *, dim_checked_for=MODEL_SETTINGS) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    pages = [OwnPage("https://me.de/a", np.array([1.0, 0.0], dtype=np.float32), title="Seite A"),
             OwnPage("https://me.de/b", np.array([0.0, 1.0], dtype=np.float32))]
    bl = BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor="x", domain_rating=50.0)
    at.session_state["frog"] = FrogImport(pages=pages, dimension=2, skipped=0)
    at.session_state["frog_name"] = "frog.csv"
    at.session_state["dim_ok"] = True
    at.session_state["probe_dim"] = 2
    if dim_checked_for is not None:
        at.session_state["dim_checked_for"] = dim_checked_for
    at.session_state["raw_backlinks"] = backlinks or [bl]
    at.session_state["recovered_for"] = [BrokenBacklink(**{**bl.__dict__, "value_rank": 1})]
    at.session_state["recovered"] = [RecoveredContent("https://c.de/x", "text", "wayback", "20240101000000")]
    at.session_state["vectors"] = [np.array([1.0, 0.0], dtype=np.float32)]
    return at


def button(at: AppTest, label: str):
    return next(b for b in at.button if b.label == label)


def test_app_renders_sidebar_and_first_sections():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    headers = [h.value for h in at.header]
    assert any(h.startswith("1.") for h in headers)
    assert any(h.startswith("2.") for h in headers)
    assert at.sidebar.selectbox[0].value == "openai"


def test_app_renders_all_five_sections_with_seeded_state():
    at = seeded_app().run()
    assert not at.exception
    numbers = sorted(h.value[0] for h in at.header if h.value[0].isdigit())
    assert numbers == ["1", "2", "3", "4", "5"]
    assert len(at.session_state["results"]) == 1
    assert at.session_state["results"][0].top[0].url == "https://me.de/a"


def test_matching_enabled_when_dimension_check_matches_settings():
    at = seeded_app().run()
    assert not at.exception
    assert button(at, "Matching starten").disabled is False
    assert any(s.value.startswith("Dimension passt") for s in at.success)


def test_matching_blocked_after_model_change():
    at = seeded_app().run()
    at.sidebar.text_input[0].set_value("other").run()
    assert not at.exception
    assert button(at, "Matching starten").disabled is True
    assert any("Dimensionscheck für die aktuellen Einstellungen erneut ausführen" in w.value for w in at.warning)
    assert not any(s.value.startswith("Dimension passt") for s in at.success)


def test_matching_blocked_without_recorded_check_settings():
    at = seeded_app(dim_checked_for=None).run()
    assert not at.exception
    assert button(at, "Matching starten").disabled is True


def test_mail_draft_uses_stable_key_and_refreshes_on_regenerate(monkeypatch):
    drafts = iter(["Erster Entwurf", "Zweiter Entwurf"])
    monkeypatch.setattr("blm.outreach.draft_mail", lambda *a, **k: next(drafts))
    at = seeded_app().run()
    key = hashlib.sha1(b"https://a.de/p|https://c.de/x").hexdigest()[:12]

    at.button(key=f"mail_{key}").click().run()
    assert not at.exception
    assert at.text_area(key=f"ta_{key}").value == "Erster Entwurf"
    assert f"draft_{key}" not in at.session_state

    at.button(key=f"mail_{key}").click().run()
    assert not at.exception
    assert at.text_area(key=f"ta_{key}").value == "Zweiter Entwurf"


def test_wayback_loop_sleeps_only_after_uncached_fetches_and_reuses_partial(monkeypatch):
    urls = [f"https://c.de/{i}" for i in range(4)]
    backlinks = [BrokenBacklink(url_from=f"https://a.de/{i}", url_to=u, domain_rating=90.0 - i)
                 for i, u in enumerate(urls)]
    fetched, slept = [], []

    def fake_recover(bl, client, cache, **kwargs):
        fetched.append(bl.url_to)
        return RecoveredContent(bl.url_to, f"text {bl.url_to}", "wayback", "20240101000000")

    # urls[0] is a cache hit, urls[1] is already in recovered_partial, urls[2] and urls[3] are misses
    monkeypatch.setattr("blm.wayback.recover_content", fake_recover)
    monkeypatch.setattr("blm.cache.JsonCache.get", lambda self, ns, key: {"hit": True} if key == urls[0] else None)
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    at = seeded_app(backlinks)
    at.session_state["recovered_partial"] = {urls[1]: RecoveredContent(urls[1], "kept", "wayback", "20230101000000")}
    at.session_state["recovered_partial_chars"] = 12000
    at.run()
    button(at, "Inhalte aus der Wayback Machine holen").click().run()

    assert not at.exception
    assert fetched == [urls[0], urls[2], urls[3]]
    assert [s for s in slept if s == 1.0] == [1.0]  # only after urls[2]; hit and last item do not sleep
    assert [r.url_to for r in at.session_state["recovered"]] == urls
    assert at.session_state["recovered"][1].text == "kept"
    assert [b.url_to for b in at.session_state["recovered_for"]] == urls
    assert "vectors" not in at.session_state and "results" not in at.session_state  # matching invalidated


def test_new_frog_upload_invalidates_matching_and_dimension_check():
    at = seeded_app().run()
    assert len(at.session_state["results"]) == 1

    csv = b"url,embedding_0,embedding_1,embedding_2\nhttps://new.de/a,1,0,0\nhttps://new.de/b,0,1,0\n"
    at.file_uploader(key="frog_upload").set_value(("new-frog.csv", csv, "text/csv")).run()

    assert not at.exception
    assert [p.url for p in at.session_state["frog"].pages] == ["https://new.de/a", "https://new.de/b"]
    assert at.session_state["frog_name"] == "new-frog.csv"
    for key in ("vectors", "results", "results_params", "dim_ok", "probe_dim", "dim_checked_for"):
        assert key not in at.session_state
    assert button(at, "Matching starten").disabled is True


def test_duplicate_backlink_pairs_get_unique_widget_keys():
    def bl(anchor):
        return BrokenBacklink(url_from="https://a.de/p", url_to="https://c.de/x", anchor=anchor, domain_rating=50.0)

    at = seeded_app([bl("eins"), bl("zwei")])
    at.session_state["recovered_for"] = [BrokenBacklink(**{**b.__dict__, "value_rank": i + 1})
                                         for i, b in enumerate([bl("eins"), bl("zwei")])]
    at.session_state["recovered"] = [RecoveredContent("https://c.de/x", "text", "wayback", "20240101000000")] * 2
    at.session_state["vectors"] = [np.array([1.0, 0.0], dtype=np.float32)] * 2
    at.run()

    assert not at.exception
    assert len(at.session_state["results"]) == 2
    base = hashlib.sha1(b"https://a.de/p|https://c.de/x").hexdigest()[:12]
    mail_keys = [b.key for b in at.button if b.key and b.key.startswith("mail_")]
    assert mail_keys == [f"mail_{base}", f"mail_{base}-1"]


def test_drafts_cleared_when_results_are_rebuilt_for_new_parameters():
    at = seeded_app()
    at.session_state["results_params"] = (0.9, True)  # differs from the default threshold 0.5
    at.session_state["ta_someold"] = "veralteter Entwurf"
    at.run()

    assert not at.exception
    assert at.session_state["results_params"] == (0.5, True)
    assert "ta_someold" not in at.session_state


def test_matching_shows_progress_and_stores_vectors(monkeypatch):
    calls = []

    def fake_embed_cached(provider, texts, cache, *, progress=None):
        calls.append(list(texts))
        if progress:
            progress(len(texts), len(texts))
        return [np.array([1.0, 0.0], dtype=np.float32) for _ in texts]

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("blm.embeddings.embed_cached", fake_embed_cached)
    at = seeded_app()
    del at.session_state["vectors"]
    at.run()
    button(at, "Matching starten").click().run()

    assert not at.exception
    assert calls == [["text"]]
    assert len(at.session_state["vectors"]) == 1
    assert len(at.session_state["results"]) == 1


def test_keys_from_environment_are_never_prefilled_into_widgets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-secret-123")
    monkeypatch.setenv("AHREFS_API_KEY", "ahrefs-secret-456")
    at = AppTest.from_file(APP, default_timeout=30).run()

    assert not at.exception
    values = {t.label: t.value for t in at.sidebar.text_input}
    assert values["Openai API-Schlüssel"] == ""
    assert values["Ahrefs-API-Schlüssel (optional)"] == ""
    assert not any("secret" in (t.value or "") for t in at.text_input)
    assert [c.value for c in at.sidebar.caption].count("Schlüssel aus Secrets/Umgebung aktiv") == 2

    # the environment key is still used: the Ahrefs fetch becomes available once a domain is entered
    next(t for t in at.text_input if t.label == "Wettbewerber-Domain").input("konkurrent.de").run()
    assert button(at, "Von Ahrefs abrufen").disabled is False


def test_no_key_caption_without_environment_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AHREFS_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert "Schlüssel aus Secrets/Umgebung aktiv" not in [c.value for c in at.sidebar.caption]
