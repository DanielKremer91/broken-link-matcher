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


def fill_sender(at: AppTest, name: str = "Daniel", domain: str = "me.de") -> AppTest:
    at.text_input(key="sender_name").input(name)
    at.text_input(key="own_domain").input(domain)
    return at.run()


def test_mail_draft_uses_stable_key_and_refreshes_on_regenerate(monkeypatch):
    drafts = iter(["Erster Entwurf", "Zweiter Entwurf"])
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("blm.outreach.draft_mail", lambda *a, **k: next(drafts))
    at = fill_sender(seeded_app().run())
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


GAP_KEYS = ("recovered", "recovered_for", "recovered_partial", "vectors", "results", "results_params")


def test_new_backlink_upload_drops_old_wayback_and_matching_state():
    at = seeded_app()
    at.session_state["recovered_partial"] = {"https://c.de/x": RecoveredContent("https://c.de/x", "t", "wayback")}
    at.run()
    assert "results" in at.session_state

    csv = b"Referring page URL,Target URL,Anchor\nhttps://neu.de/p,https://c.de/neu,neu\n"
    at.file_uploader(key="bl_upload").set_value(("neu.csv", csv, "text/csv")).run()
    button(at, "Backlinks übernehmen").click().run()

    assert not at.exception
    assert [b.url_to for b in at.session_state["raw_backlinks"]] == ["https://c.de/neu"]
    for key in GAP_KEYS:
        assert key not in at.session_state, key


def test_ahrefs_fetch_drops_old_wayback_and_matching_state(monkeypatch):
    monkeypatch.setenv("AHREFS_API_KEY", "ah-test")
    monkeypatch.setattr("blm.ingest.ahrefs_api.fetch_broken_backlinks",
                        lambda *a, **k: [BrokenBacklink(url_from="https://neu.de/p", url_to="https://c.de/neu")])
    at = seeded_app()
    at.session_state["recovered_partial"] = {"https://c.de/x": RecoveredContent("https://c.de/x", "t", "wayback")}
    at.run()
    next(t for t in at.text_input if t.label == "Wettbewerber-Domain").input("konkurrent.de").run()
    button(at, "Von Ahrefs abrufen").click().run()

    assert not at.exception
    for key in GAP_KEYS:
        assert key not in at.session_state, key


def test_warning_when_recovered_texts_belong_to_another_selection():
    at = seeded_app()
    at.session_state["recovered_for"] = [BrokenBacklink(url_from="https://alt.de/p", url_to="https://c.de/alt", value_rank=1)]
    at.run()
    assert not at.exception
    assert any("Filter oder Backlinks geändert" in w.value for w in at.warning)


def test_no_selection_warning_when_recovered_texts_match_ranking():
    at = seeded_app().run()
    assert not any("Filter oder Backlinks geändert" in w.value for w in at.warning)


def test_contact_is_sent_in_user_agent_for_wayback_and_live_check(monkeypatch):
    seen = {}

    def fake_recover(bl, client, cache, **kwargs):
        seen["wayback"] = kwargs.get("user_agent")
        return RecoveredContent(bl.url_to, "text", "wayback", "20240101000000")

    def fake_verify(results, client, **kwargs):
        seen["verify"] = kwargs.get("user_agent")

    monkeypatch.setattr("blm.wayback.recover_content", fake_recover)
    monkeypatch.setattr("blm.verify.verify_results", fake_verify)
    monkeypatch.setattr("blm.cache.JsonCache.get", lambda self, ns, key: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    at = seeded_app().run()
    at.text_input(key="ua_contact").input("seo@me.de").run()
    button(at, "Live prüfen: Ziel noch 404 und Link noch vorhanden?").click().run()
    button(at, "Inhalte aus der Wayback Machine holen").click().run()

    assert not at.exception
    assert "seo@me.de" in seen["wayback"] and "seo@me.de" in seen["verify"]


def test_frog_model_hint_expander_is_shown():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert "Welches Modell habe ich im Frog?" in [e.label for e in at.expander]
    text = " ".join(m.value for m in at.markdown)
    for needle in ("text-embedding-3-small", "gemini-embedding-001", "nomic-embed-text", "exakt"):
        assert needle in text


def test_wayback_summary_counts_errors():
    at = seeded_app()
    at.session_state["recovered"] = [RecoveredContent("https://c.de/x", "fallback text", "fallback", error="Wayback-Fehler: HTTP 503")]
    at.run()
    assert not at.exception
    assert any("Fehler: 1" in m.value for m in at.markdown)


def test_buttons_need_api_key_for_openai(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = fill_sender(seeded_app().run())
    assert not at.exception
    assert button(at, "Dimensionscheck gegen gewähltes Modell").disabled is True
    assert all(b.disabled for b in at.button if b.key and b.key.startswith("mail_"))
    captions = [c.value for c in at.caption]
    assert any("API-Schlüssel" in c for c in captions)


def test_buttons_enabled_with_api_key_and_sender(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    at = fill_sender(seeded_app().run())
    assert button(at, "Dimensionscheck gegen gewähltes Modell").disabled is False
    mail = [b for b in at.button if b.key and b.key.startswith("mail_")]
    assert mail and not any(b.disabled for b in mail)


def test_ollama_never_blocked_by_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    at = seeded_app().run()
    at.sidebar.selectbox[0].select("ollama").run()
    at = fill_sender(at)
    assert button(at, "Dimensionscheck gegen gewähltes Modell").disabled is False
    assert not any(b.disabled for b in at.button if b.key and b.key.startswith("mail_"))


def test_draft_needs_sender_name_and_domain(monkeypatch):
    seen = []
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr("blm.outreach.draft_mail", lambda row, name, domain, **k: seen.append((name, domain)) or "Entwurf")
    at = seeded_app().run()
    assert all(b.disabled for b in at.button if b.key and b.key.startswith("mail_"))
    assert "Name und Domain in der Seitenleiste eintragen" in [c.value for c in at.caption]

    at = fill_sender(at, name="Daniel", domain="")
    assert all(b.disabled for b in at.button if b.key and b.key.startswith("mail_"))

    at = fill_sender(at, name="Daniel", domain="me.de")
    key = hashlib.sha1(b"https://a.de/p|https://c.de/x").hexdigest()[:12]
    at.button(key=f"mail_{key}").click().run()
    assert not at.exception
    assert seen == [("Daniel", "me.de")]


def test_live_check_shows_verification_and_survives_rebuild(monkeypatch):
    def fake_verify(results, client, **kwargs):
        for r in results:
            r.verification = "confirmed"

    monkeypatch.setattr("blm.verify.verify_results", fake_verify)
    at = seeded_app().run()
    button(at, "Live prüfen: Ziel noch 404 und Link noch vorhanden?").click().run()

    assert not at.exception
    assert any("Verifikation abgeschlossen" in s.value for s in at.success)
    assert any("Verifikation: confirmed" in m.value for m in at.markdown)

    threshold = next(sl for sl in at.slider if sl.label.startswith("Schwellwert"))
    threshold.set_value(0.3).run()  # threshold change rebuilds the results
    assert not at.exception
    assert at.session_state["results_params"] == (0.3, True)
    assert at.session_state["results"][0].verification == "confirmed"


def test_fallback_is_built_per_backlink_and_not_kept_in_partial(monkeypatch):
    fetched = []

    def fake_recover(bl, client, cache, **kwargs):
        fetched.append(bl.url_to)
        return RecoveredContent(bl.url_to, f"Anker {bl.anchor}", "fallback", error="Kein Snapshot mit Status 200")

    monkeypatch.setattr("blm.wayback.recover_content", fake_recover)
    monkeypatch.setattr("blm.cache.JsonCache.get", lambda self, ns, key: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    backlinks = [BrokenBacklink(url_from=f"https://a.de/{i}", url_to="https://c.de/tot", anchor=anchor, domain_rating=90.0 - i)
                 for i, anchor in enumerate(["eins", "zwei"])]
    at = seeded_app(backlinks).run()
    button(at, "Inhalte aus der Wayback Machine holen").click().run()

    assert not at.exception
    assert fetched == ["https://c.de/tot"]  # the dead URL is queried once per run
    texts = [r.text for r in at.session_state["recovered"]]
    assert "eins" in texts[0] and "zwei" in texts[1] and "eins" not in texts[1]
    assert [r.error for r in at.session_state["recovered"]] == ["Kein Snapshot mit Status 200"] * 2
    assert at.session_state["recovered_partial"] == {}


def test_content_gap_rows_get_no_draft_button(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    at = seeded_app()
    at.session_state["vectors"] = [np.array([-1.0, 0.0], dtype=np.float32)]  # best score 0.0 < 0.5
    at = fill_sender(at.run())
    assert not at.exception
    assert at.session_state["results"][0].is_content_gap
    assert not any(b.key and b.key.startswith("mail_") for b in at.button)
    assert any("Content-Gap" in c.value for c in at.caption)


def test_recognised_columns_show_success_message():
    from pathlib import Path as _P

    at = AppTest.from_file(str(_P(__file__).resolve().parent.parent / "app.py"), default_timeout=30)
    at.session_state["frog"] = FrogImport(pages=[OwnPage("https://me.de/a", np.array([1.0, 0.0], dtype=np.float32))], dimension=2, skipped=0)
    at.session_state["frog_name"] = "frog.csv"
    at.run()
    csv_path = _P(__file__).resolve().parent.parent / "examples" / "broken-backlinks-ahrefs-com.csv"
    at.file_uploader(key="bl_upload").set_value(("broken-backlinks-ahrefs-com.csv", csv_path.read_bytes(), "text/csv")).run()
    assert not at.exception
    assert any("9 Spalten automatisch erkannt (15 Zeilen)" in s.value for s in at.success)
