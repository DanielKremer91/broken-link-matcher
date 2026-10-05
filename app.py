"""Broken Link Matcher: Streamlit UI. Wiring only; all logic lives in blm/."""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Callable

import httpx
import pandas as pd
import streamlit as st

from blm.cache import JsonCache
from blm.embeddings import DEFAULT_EMBED_MODELS, PROVIDERS, EmbeddingError, embed_cached, make_provider
from blm.export import results_to_dataframe, source_label, to_csv_bytes, to_xlsx_bytes
from blm.ingest.ahrefs_api import AhrefsError, describe_filters, fetch_broken_backlinks
from blm.ingest.backlinks_csv import OPTIONAL_FIELDS, REQUIRED_FIELDS, detect_columns, parse_backlinks
from blm.ingest.frog_csv import detect_frog_columns, load_frog_embeddings
from blm.ingest.tables import describe_table_info, read_table_info
from blm.matcher import build_results
from blm.outreach import DEFAULT_CHAT_MODELS, OutreachError, draft_mail
from blm.ranking import SORT_FIELDS, rank_backlinks
from blm.verify import verify_results
from blm.wayback import fallback_content, recover_content, user_agent

st.set_page_config(page_title="ONE Broken Link Matcher", page_icon="🔗", layout="wide")
st.markdown(
    """
<div style="display: flex; align-items: center; gap: 20px; margin-bottom: 0.5rem;">
  <img src="https://onebeyondsearch.com/img/ONE_beyond_search%C3%94%C3%87%C3%B4gradient%20%282%29.png" alt="ONE Beyond Search" style="height: 60px;">
</div>
<style>
div[data-testid="stDownloadButton"] > button {
    background-color: #d7263d !important; color: white !important; border: 1px solid #b51f33 !important;
}
div[data-testid="stDownloadButton"] > button:hover { background-color: #b51f33 !important; color: white !important; }
</style>
""",
    unsafe_allow_html=True,
)
S = st.session_state
CACHE = JsonCache(Path(__file__).parent / ".cache")
KEY_FROM_SECRETS = "Schlüssel aus Secrets/Umgebung aktiv"
KEY_MISSING_HINT = "API-Schlüssel in der Seitenleiste eintragen (oder über Secrets/Umgebung setzen)."
SENDER_MISSING_HINT = "Name und Domain in der Seitenleiste eintragen"
FROG_MODEL_HINT = """
| Anbieter im Frog | Anbieter hier | Typische Modellnamen |
|---|---|---|
| OpenAI | openai | text-embedding-3-small, text-embedding-3-large |
| Gemini | gemini | gemini-embedding-001, text-embedding-004 |
| Ollama | ollama | nomic-embed-text, mxbai-embed-large |

Den Modellnamen findest du in der Frog-Konfiguration beim Embeddings-Anbieter. Er muss hier exakt gleich
eingetragen sein, sonst liegen die Vektoren in unterschiedlichen Räumen.
"""
INFO_TEXT = """
**Wofür ist das Tool?** Broken Link Building mit semantischem Matching: Du lädst die toten URLs eines Wettbewerbers
samt ihrer Backlinks, das Tool rekonstruiert den früheren Inhalt jeder toten URL aus der Wayback Machine, berechnet
Embeddings und findet die inhaltlich passendste Seite deiner eigenen Domain als Ersatzziel. Wo keine Seite von dir
ausreichend passt, entsteht als Nebenprodukt eine Liste von Content-Gaps.

**Voraussetzungen**
- Ein Screaming-Frog-Crawl deiner eigenen Domain mit aktivierten Embeddings und der Export der Embeddings (CSV oder XLSX).
- Ein Export der Broken Backlinks des Wettbewerbers aus Ahrefs oder einem anderen Tool, alternativ ein Ahrefs-API-Schlüssel.
- Ein API-Schlüssel für denselben Embedding-Anbieter, den du im Frog verwendet hast (bei Ollama genügt die lokale URL).

**Ablauf**
1. Eigene Domain: Frog-Embeddings hochladen und per Dimensionscheck prüfen, ob das gewählte Modell passt.
2. Wettbewerber-Backlinks: CSV/XLSX hochladen oder per Ahrefs-API laden, filtern und nach Wert sortieren.
3. Abruf aus der Wayback Machine: den früheren Inhalt der toten URLs holen.
4. Matching: Embeddings berechnen, die passendste eigene Seite je Backlink bestimmen, Content-Gaps markieren.
5. Verifikation und Outreach: optional live prüfen, Ergebnisse als CSV oder Excel laden, Mail-Entwürfe erzeugen.

"Los geht's" führt den Dimensionscheck aus Schritt 1 sowie die Schritte 3 und 4 in einem Durchlauf aus. Die einzelnen Buttons bleiben für erneute Läufe erhalten.

**Hinweise**
- Texte werden nie erfunden: Sie stammen aus der Wayback Machine oder werden aus Ahrefs-Feldern (Anker, Kontext, Titel) zusammengesetzt.
- Der einzige generierte Text ist der optionale Mail-Entwurf. Es wird nichts versendet.
- API-Schlüssel bleiben in dieser Sitzung und werden nicht gespeichert. Texte aus der Wayback Machine und Embeddings landen im Ordner `.cache`.
- Kosten: Ahrefs berechnet Units pro abgerufener Zeile, der Embedding-Anbieter Tokens pro toter URL.
- Derselbe Ablauf steht als Kommandozeile für Claude Code zur Verfügung (`cli.py`, siehe `docs/agentic-workflow.md`).
"""
FROG_WIDE_OPTION = "(Spalten embedding_0 bis embedding_N)"
SORT_LABELS = {"domain_rating": "Domain Rating", "url_rating": "URL Rating", "page_traffic": "Seitentraffic"}


def secret(name: str) -> str:
    """Env var or st.secrets fallback for a key; never persisted and never sent to the browser."""
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
    provider = st.selectbox(
        "Embedding-Anbieter (wie im Screaming Frog)", PROVIDERS,
        help="Derselbe Anbieter, mit dem der Screaming Frog die Embeddings deiner Domain erzeugt hat. Andere Anbieter liefern nicht vergleichbare Vektoren.")
    embed_model = st.text_input(
        "Embedding-Modell (exakt wie im Frog)", value=DEFAULT_EMBED_MODELS[provider],
        help="Exakt der Modellname aus der Frog-Konfiguration. Weicht er ab, scheitert der Dimensionscheck oder die Scores sind wertlos.")
    if provider == "ollama":
        base_url = st.text_input("Ollama-URL", value="http://localhost:11434",
                                 help="Adresse deines lokalen Ollama-Servers. Ollama braucht keinen API-Schlüssel.")
        api_key = None
    else:
        base_url = None
        # never prefill a secret: widget values are serialised to the browser
        typed_key = st.text_input(
            f"{provider.capitalize()} API-Schlüssel", type="password", value="",
            help="Schlüssel des Embedding-Anbieters. Er wird nur in dieser Sitzung gehalten. Alternativ per Umgebungsvariable oder Secrets-Datei setzen.")
        api_key = typed_key or secret(f"{provider}_api_key")
        if api_key and not typed_key:
            st.caption(KEY_FROM_SECRETS)
    chat_model = st.text_input("Chat-Modell für Mail-Entwürfe", value=DEFAULT_CHAT_MODELS[provider],
                               help="Nur für die optionalen Mail-Entwürfe in Schritt 5.")
    st.divider()
    typed_ahrefs = st.text_input(
        "Ahrefs-API-Schlüssel (optional)", type="password", value="",
        help="Optional. Nur nötig, wenn du Backlinks direkt per API laden willst statt per CSV-Upload.")
    ahrefs_key = typed_ahrefs or secret("ahrefs_api_key")
    if ahrefs_key and not typed_ahrefs:
        st.caption(KEY_FROM_SECRETS)
    st.divider()
    sender_name = st.text_input("Dein Name (für Mail-Entwürfe)", key="sender_name",
                                help="Erscheint im Mail-Entwurf als Absender.").strip()
    own_domain = st.text_input("Deine Domain (für Mail-Entwürfe)", key="own_domain",
                               help="Erscheint im Mail-Entwurf als Absender.").strip()
    contact = st.text_input(
        "Kontakt im User-Agent (optional)", key="ua_contact",
        help="E-Mail oder URL, die bei Abrufen der Wayback Machine und der linkgebenden Seiten mitgesendet wird. "
             "So kann dich ein Seitenbetreiber erreichen, falls der Abruf stört. archive.org bittet darum.")
    agent = user_agent(contact)
    st.divider()
    if st.button("Cache leeren", help="Löscht gespeicherte Texte aus der Wayback Machine und Embeddings. Danach dauert der nächste Lauf wieder länger."):
        st.success(f"{CACHE.clear()} Einträge gelöscht")
    st.caption("Schlüssel bleiben in dieser Sitzung und werden nicht gespeichert.")


def clear_drafts() -> None:
    """Drop all mail drafts (the text areas hold the draft state)."""
    for key in list(S.keys()):
        if key.startswith("ta_"):
            del S[key]


def invalidate_matching() -> None:
    """Drop everything derived from the Frog import or the recovered texts."""
    for key in ("vectors", "results", "results_params"):
        S.pop(key, None)
    clear_drafts()


def reset_backlink_state() -> None:
    """A new backlink set makes recovered texts and everything after them stale."""
    for key in ("recovered_partial", "recovered", "recovered_for"):
        S.pop(key, None)
    invalidate_matching()


def upload_id(f) -> str:
    """Identify an uploaded file; file_id changes on every new upload, name is the fallback."""
    return getattr(f, "file_id", None) or f.name


def provider_or_error(report: Callable[[str], object] = st.error):
    try:
        return make_provider(provider, embed_model, api_key=api_key, base_url=base_url)
    except EmbeddingError as exc:
        report(str(exc))
        return None


key_missing = provider != "ollama" and not api_key  # Ollama needs no key
dim_settings = (provider, embed_model, base_url)


def dim_is_valid() -> bool:
    """The recorded dimension check passed for the current provider settings."""
    return S.get("dim_ok") is True and S.get("dim_checked_for") == dim_settings


def run_dimension_check(report: Callable[[str], object] = st.error) -> bool:
    """Embed a probe text and compare its length with the Frog vectors; True when they match.

    Provider errors go to ``report``; a mismatch is shown by step 1 from the stored state.
    """
    prov = provider_or_error(report)
    if prov is None:
        return False
    try:
        S["probe_dim"] = prov.probe_dimension()
    except EmbeddingError as exc:
        report(str(exc))
        return False
    S["dim_ok"] = S["probe_dim"] == S["frog"].dimension
    S["dim_checked_for"] = dim_settings
    return S["dim_ok"]


def run_wayback() -> None:
    """Recover the text of every ranked dead URL; snapshot texts are reused across runs."""
    ranked = S["ranked"]
    max_chars = int(S.get("max_chars", 12000))  # widget of step 3, may not be rendered yet
    if S.get("recovered_partial_chars") != max_chars:
        S["recovered_partial"] = {}  # texts cut at a different length are not reusable
        S["recovered_partial_chars"] = max_chars
    # only snapshot texts are kept across runs: they belong to the dead URL, while a
    # fallback is built from one backlink's own anchor and context
    partial = S.setdefault("recovered_partial", {})
    failed: dict[str, str | None] = {}  # dead URL -> error of this run, fallback per backlink
    recovered = []
    bar = st.progress(0.0, text="Starte …")
    with httpx.Client() as client:
        for i, bl in enumerate(ranked, start=1):
            if bl.url_to in partial:
                rc = partial[bl.url_to]
            elif bl.url_to in failed:
                rc = fallback_content(bl, failed[bl.url_to], max_chars)
            else:
                cached = CACHE.get("wayback", bl.url_to) is not None
                rc = recover_content(bl, client, CACHE, max_chars=max_chars, user_agent=agent)
                if rc.source == "wayback":
                    partial[bl.url_to] = rc
                else:
                    failed[bl.url_to] = rc.error
                if not cached and i < len(ranked):
                    time.sleep(1.0)
            recovered.append(rc)
            bar.progress(i / len(ranked), text=f"{i}/{len(ranked)}: {bl.url_to}")
    S["recovered_for"] = ranked
    S["recovered"] = recovered
    invalidate_matching()


def run_matching(report: Callable[[str], object] = st.error) -> bool:
    """Embed the recovered texts; the results are built from the vectors in step 4."""
    prov = provider_or_error(report)
    if prov is None:
        return False
    texts = [r.text for r in S["recovered"]]
    idx = [i for i, t in enumerate(texts) if t]
    try:
        bar = st.progress(0.0, text="Embeddings werden berechnet …")
        fresh = embed_cached(prov, [texts[i] for i in idx], CACHE,
                             progress=lambda done, total: bar.progress(done / total, text=f"Embeddings: {done}/{total} Texte"))
        bar.progress(1.0, text="Embeddings fertig.")
    except EmbeddingError as exc:
        report(str(exc))
        return False
    vectors = [None] * len(texts)
    for j, i in enumerate(idx):
        vectors[i] = fresh[j]
    S["vectors"] = vectors
    S.pop("results_params", None)
    return True


def run_all() -> str | None:
    """One click for dimension check, Wayback Machine fetch and matching; stops at the first failure.

    Returns None on success, otherwise the error text to show after the rerun.
    """
    errors: list[str] = []
    if dim_is_valid():
        st.write("Dimensionscheck: bereits bestanden.")
    else:
        st.write("Dimensionscheck …")
        if not run_dimension_check(report=errors.append):
            # a mismatch has no provider error; step 1 shows its details from the stored state
            return errors[0] if errors else "Die Dimension passt nicht zum Frog-Export, Details in Schritt 1."
    st.write("Abruf aus der Wayback Machine …")
    run_wayback()
    st.write("Matching …")
    if not run_matching(report=errors.append):
        return errors[0] if errors else "Matching fehlgeschlagen."
    return None


def next_step_hint() -> tuple[str, str]:
    """(kind, text) for the guidance box: what the user should do next."""
    if "frog" not in S:
        return "info", "Nächster Schritt: Screaming-Frog-Export in Schritt 1 hochladen."
    if "ranked" not in S:
        return "info", "Nächster Schritt: Broken Backlinks in Schritt 2 hochladen oder per API laden."
    if not S["ranked"]:
        return "warning", "Die Filter in Schritt 2 lassen keine Backlinks übrig. Mindest-DR oder Schalter lockern."
    if key_missing:
        return "warning", "Nächster Schritt: API-Schlüssel in der Seitenleiste eintragen, dann \"Los geht's\" klicken."
    if "recovered_for" in S and S["recovered_for"] != S["ranked"]:
        return "warning", "Filter geändert. \"Los geht's\" erneut klicken, damit die Ergebnisse zur aktuellen Auswahl passen."
    if S.get("results"):
        return "success", "Ergebnisse liegen vor. Optional in Schritt 5 live prüfen, exportieren oder Mail-Entwürfe erzeugen."
    return "info", "Alles bereit. Klicke \"Los geht's\" für Dimensionscheck, Abruf aus der Wayback Machine und Matching in einem Durchlauf."


def missing_inputs() -> list[str]:
    """What still blocks the one-click run."""
    missing = []
    if "frog" not in S:
        missing.append("Screaming-Frog-Export (Schritt 1)")
    if "ranked" not in S:
        missing.append("Broken Backlinks (Schritt 2)")
    elif not S["ranked"]:
        missing.append("mindestens ein Backlink nach den Filtern (Schritt 2)")
    if key_missing:
        missing.append("API-Schlüssel (Seitenleiste)")
    return missing


st.title("Broken Link Matcher")
st.markdown(
    """
<div style="background-color: #f2f2f2; color: #000000; padding: 15px 20px; border-radius: 6px; font-size: 0.9em; max-width: 850px; margin-bottom: 1.5em; line-height: 1.5;">
  Entwickelt von <a href="https://www.linkedin.com/in/daniel-kremer-b38176264/" target="_blank">Daniel Kremer</a> von <a href="https://onebeyondsearch.com/" target="_blank">ONE Beyond Search</a> &nbsp;|&nbsp;
  Vorgestellt auf der SEOKomm 2026 &nbsp;|&nbsp;
  Folge mir auf <a href="https://www.linkedin.com/in/daniel-kremer-b38176264/" target="_blank">LinkedIn</a> für mehr SEO-Insights und Tool-Updates
</div>
""",
    unsafe_allow_html=True,
)
with st.expander("ℹ️ Was macht dieses Tool und wie nutze ich es?", expanded=False):
    st.markdown(INFO_TEXT)
# filled at the end of the script, so hint and button see this run's uploads and filters
next_step_box = st.container()

# ----------------------------------------------------------------- 1. own domain
st.header("1. Eigene Domain (Screaming-Frog-Embeddings)")
frog_file = st.file_uploader(
    "Embeddings-Export aus dem Screaming Frog (CSV, XLSX oder NDJSON)", type=["csv", "xlsx", "xlsm", "tsv", "txt", "ndjson", "jsonl"], key="frog_upload",
    help="Embeddings als CSV, TSV, TXT, XLSX oder NDJSON (MCP). Erkannt: url plus embedding_N oder Address plus "
         "Vektor-Spalte. Nicht mit Excel als CSV speichern, Excel kürzt lange Vektoren.")
with st.expander("Welches Modell habe ich im Frog?"):
    st.markdown(FROG_MODEL_HINT)


def accept_frog(imp, f) -> None:
    """Store a successful Frog import and drop everything derived from the previous one."""
    S["frog"] = imp
    S["frog_name"] = f.name
    S["frog_upload_id"] = upload_id(f)
    for key in ("dim_ok", "probe_dim", "dim_checked_for", "frog_failed_id", "frog_error", "frog_columns"):
        S.pop(key, None)
    invalidate_matching()


frog_id = upload_id(frog_file) if frog_file is not None else None
if frog_file is not None and frog_id not in (S.get("frog_upload_id"), S.get("frog_failed_id")):
    try:
        accept_frog(load_frog_embeddings(frog_file), frog_file)
    except ValueError as exc:
        S["frog_failed_id"] = frog_id
        S["frog_error"] = str(exc)
        try:  # read once more to offer a manual column mapping
            S["frog_columns"] = detect_frog_columns(read_table_info(frog_file, filename=frog_file.name)[0])
        except ValueError:
            S.pop("frog_columns", None)
if frog_file is not None and frog_id == S.get("frog_failed_id"):
    st.error(S["frog_error"])
    frog_cols = S.get("frog_columns")
    if frog_cols is not None and frog_cols.columns:
        st.write("Spalten selbst zuordnen:")
        options = frog_cols.columns
        vec_options = ([FROG_WIDE_OPTION] if frog_cols.wide else []) + options
        m1, m2 = st.columns(2)
        url_choice = m1.selectbox(
            "URL-Spalte", options, key=f"frog_map_url_{frog_id}",
            index=options.index(frog_cols.url_col) if frog_cols.url_col in options else 0,
            help="Spalte mit den Adressen deiner Seiten, im Frog meist Address.")
        vec_choice = m2.selectbox(
            "Embedding-Spalte", vec_options, key=f"frog_map_vec_{frog_id}",
            index=vec_options.index(frog_cols.vector_col) if frog_cols.vector_col in vec_options else (
                0 if frog_cols.wide else min(1, len(vec_options) - 1)),
            help="Spalte mit dem Vektor als Zahlenliste, z. B. 0.1,0.2,0.3 oder [0.1, 0.2], oder die Spalten embedding_0 bis embedding_N.")
        if st.button("Zuordnung übernehmen", help="Liest die Datei erneut mit den gewählten Spalten für URL und Embedding."):
            try:
                vector_col = None if vec_choice == FROG_WIDE_OPTION else vec_choice
                accept_frog(load_frog_embeddings(frog_file, url_col=url_choice, vector_col=vector_col), frog_file)
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
dim_valid = dim_is_valid()
if "frog" in S:
    imp = S["frog"]
    st.write(f"{len(imp.pages)} URLs, Vektordimension {imp.dimension}, {imp.skipped} Zeilen übersprungen.")
    if getattr(imp, "table", None) is not None:
        st.caption(describe_table_info(imp.table))
    if key_missing:
        st.caption(KEY_MISSING_HINT)
    if st.button("Dimensionscheck gegen gewähltes Modell", disabled=key_missing,
                 help="Embeddet einen Probetext mit dem gewählten Modell und vergleicht die Vektorlänge mit deiner Frog-Datei."):
        run_dimension_check()
        dim_valid = dim_is_valid()
    if "probe_dim" in S:
        if S.get("dim_checked_for") != dim_settings:
            st.warning("Dimensionscheck für die aktuellen Einstellungen erneut ausführen.")
        elif S.get("dim_ok"):
            st.success(f"Dimension passt ({S['probe_dim']}).")
        else:
            st.error(f"Dimension passt nicht: Frog-Export {imp.dimension}, Modell {S['probe_dim']}. Wähle exakt das Modell, das im Frog konfiguriert ist.")

# ----------------------------------------------------------------- 2. backlinks
st.header("2. Wettbewerber-Backlinks")
tab_csv, tab_api = st.tabs(["CSV/XLSX-Upload", "Ahrefs-API"])
with tab_csv:
    bl_file = st.file_uploader(
        "Broken-Backlinks-Export (Ahrefs oder anderes Tool)", type=["csv", "xlsx", "xlsm", "xls", "tsv", "txt"], key="bl_upload",
        help="Export aus Ahrefs oder einem anderen Tool als CSV, TSV, TXT oder XLSX. Spalten werden automatisch erkannt. "
             "Mit Excel gespeicherte CSVs können Zahlen als Datum enthalten.")
    if bl_file is not None and S.get("bl_upload_id") != upload_id(bl_file):
        try:
            new_df, new_info = read_table_info(bl_file, filename=bl_file.name)
            new_mapping = detect_columns(new_df)
            S["bl_df"] = new_df
            S["bl_info"] = new_info
            S["bl_mapping"] = new_mapping
            S["bl_name"] = bl_file.name
            S["bl_upload_id"] = upload_id(bl_file)
            S.pop("bl_report", None)
            if not new_mapping.missing:
                # all required columns recognised: take the file over right away, no extra click
                parse_report: dict = {}
                S["raw_backlinks"] = parse_backlinks(new_df, new_mapping.mapping, report=parse_report)
                S["bl_report"] = parse_report
                reset_backlink_state()
        except Exception as exc:  # pandas raises many types for malformed files
            # read_table_info's ValueErrors already carry the German prefix
            st.error(str(exc) if isinstance(exc, ValueError) else f"Datei konnte nicht gelesen werden: {exc}")
    if "bl_df" in S:
        cm = S["bl_mapping"]
        mapping = dict(cm.mapping)
        if cm.missing:
            st.warning("Pflichtspalten nicht erkannt. Bitte zuordnen.")
        else:
            st.success(f"{len(cm.mapping)} Spalten automatisch erkannt, {len(S.get('raw_backlinks', []))} Backlinks übernommen ({len(S['bl_df'])} Zeilen).")
        if S.get("bl_info") is not None:
            st.caption(describe_table_info(S["bl_info"]))
        repaired_auto = (S.get("bl_report") or {}).get("excel_dates_repaired", 0)
        if repaired_auto > 0:
            st.warning(f"{repaired_auto} Zahlenwerte sahen wie Excel-Datumsangaben aus (z. B. '04. Jun' für 4.6) "
                       "und wurden zurückgerechnet. Tipp: CSV nicht mit Excel speichern.")
        show_mapping = cm.missing or st.checkbox("Spaltenzuordnung anpassen",
                                     help="Ordne die Spalten deiner Datei den Feldern des Tools selbst zu, falls die automatische Erkennung falsch liegt.")
        if show_mapping:
            options = ["(keine)"] + cm.columns
            for field in REQUIRED_FIELDS + OPTIONAL_FIELDS:
                current = mapping.get(field, "(keine)")
                choice = st.selectbox(field, options, index=options.index(current) if current in options else 0, key=f"map_{field}",
                                      help=f"Spalte deiner Datei, die als Feld \"{field}\" gelesen wird. \"(keine)\" lässt das Feld leer.")
                if choice == "(keine)":
                    mapping.pop(field, None)
                else:
                    mapping[field] = choice
            if st.button("Zuordnung übernehmen", help="Übernimmt die Datei mit der gewählten Spaltenzuordnung als Backlink-Liste und verwirft spätere Schritte."):
                try:
                    parse_report = {}
                    S["raw_backlinks"] = parse_backlinks(S["bl_df"], mapping, report=parse_report)
                    S["bl_report"] = parse_report
                    reset_backlink_state()
                    st.success(f"{len(S['raw_backlinks'])} Backlinks übernommen.")
                except ValueError as exc:
                    st.error(str(exc))
with tab_api:
    target = st.text_input("Wettbewerber-Domain", placeholder="konkurrent.de",
                           help="Domain, deren tote Backlink-Ziele du abrufen willst, ohne https://, z. B. konkurrent.de. Subdomains sind eingeschlossen.")
    api_limit = st.number_input("Maximale Zeilen", min_value=10, max_value=1000, value=100, step=10,
                                help="Obergrenze der abgerufenen Zeilen. Jede Zeile kostet Ahrefs-API-Units, ein kleiner Wert für den ersten Test spart Budget.")
    include_traffic = st.checkbox("Seitentraffic mitladen (10 API-Units extra pro Zeile)",
                                  help="Lädt den geschätzten Traffic der linkgebenden Seite für die Sortierung nach Seitentraffic. Kostet 10 Units extra pro Zeile.")
    f1, f2, f3, f4 = st.columns(4)
    api_dofollow = f1.checkbox("Nur Dofollow", value=True, key="api_dofollow",
                               help="Ahrefs liefert nur Links ohne nofollow, sponsored oder ugc. Nur sie geben Linkkraft weiter.")
    api_content = f2.checkbox("Nur Content-Links", value=True, key="api_content",
                              help="Ahrefs liefert nur Links aus dem redaktionellen Inhalt, keine aus Navigation, Footer oder Sidebar.")
    api_exclude_spam = f3.checkbox("Spam-Domains ausschließen", value=True, key="api_exclude_spam",
                                   help="Lässt Domains weg, die Ahrefs als Spam einstuft. Vermeidet wertlose Linkquellen.")
    api_dead_only = f4.checkbox("Nur tote Ziele (404/410)", value=True, key="api_dead_only",
                                help="Nur Links, deren Ziel-URL aktuell mit 404 oder 410 antwortet. Ohne den Haken kommen auch andere Fehlercodes wie 403 oder 500 mit.")
    api_min_dr = st.number_input("Mindest-DR (API-seitig)", min_value=0, max_value=100, value=0, step=5,
                                 help="Ahrefs liefert nur linkgebende Domains ab diesem Domain Rating. 0 schaltet den Filter aus.")
    api_filters = dict(dofollow_only=api_dofollow, content_only=api_content, exclude_spam=api_exclude_spam,
                       dead_only=api_dead_only, min_dr=float(api_min_dr))
    st.caption("Aktive API-Filter: " + describe_filters(**api_filters))
    st.caption("Die Filter kosten nichts extra. Units fallen pro zurückgegebener Zeile an, weniger Treffer heißen also weniger Units.")
    st.caption("Die Filter unterhalb der Tabelle (Schritt 2) wirken zusätzlich auf die geladenen Zeilen.")
    if not ahrefs_key:
        st.caption("Ohne Ahrefs-API-Schlüssel steht nur der CSV-Weg zur Verfügung.")
    if st.button("Von Ahrefs abrufen", disabled=not (ahrefs_key and target),
                 help="Lädt die Broken Backlinks der Domain über die Ahrefs-API v3, ein Link pro verweisender Domain. Verbraucht API-Units."):
        try:
            S["raw_backlinks"] = fetch_broken_backlinks(ahrefs_key, target, limit=int(api_limit), include_traffic=include_traffic, **api_filters)
            reset_backlink_state()
            st.success(f"{len(S['raw_backlinks'])} Backlinks geladen.")
        except AhrefsError as exc:
            st.error(f"{exc} Alternative: CSV-Export aus Ahrefs hochladen.")

if "raw_backlinks" in S:
    c1, c2, c3, c4, c5 = st.columns(5)
    dofollow_only = c1.checkbox("Nur Dofollow", value=True,
                                help="Blendet Links mit nofollow, sponsored oder ugc aus. Nur Dofollow-Links geben Linkkraft weiter. Unbekannte Werte bleiben stehen.")
    content_only = c2.checkbox("Nur Content-Links", value=True,
                               help="Blendet Links aus Navigation, Footer und Sidebar aus. Redaktionelle Links im Fließtext sind meist leichter zu ersetzen.")
    min_dr = c3.slider("Mindest-DR", 0, 100, 0,
                       help="Blendet linkgebende Domains unter diesem Domain Rating aus, damit nur starke Quellen in der Liste bleiben. Unbekannte Werte bleiben stehen.")
    sort_by = c4.selectbox("Sortieren nach", SORT_FIELDS, format_func=SORT_LABELS.get,
                           help="Kennzahl für den Rang der Zeilen. Die Obergrenze schneidet nach dieser Sortierung ab.")
    limit = c5.number_input("Obergrenze", min_value=1, max_value=1000, value=100,
                            help="Höchstzahl der Backlinks für Wayback-Machine-Abruf und Matching. Weniger Zeilen bedeuten kürzere Läufe und geringere Embedding-Kosten.")
    S["ranked"] = rank_backlinks(S["raw_backlinks"], dofollow_only=dofollow_only, content_only=content_only, min_dr=float(min_dr), sort_by=sort_by, limit=int(limit))
    preview = pd.DataFrame([{"Rang": b.value_rank, "Linkgebende URL": b.url_from, "DR": b.domain_rating, "UR": b.url_rating,
                             "Traffic": b.page_traffic, "Anker": b.anchor, "Tote URL": b.url_to} for b in S["ranked"]])
    st.dataframe(preview, width="stretch", hide_index=True)

# ----------------------------------------------------------------- 3. wayback
if "ranked" in S:
    st.header("3. Abruf aus der Wayback Machine")
    st.number_input("Maximale Zeichen pro Text", min_value=1000, max_value=50000, value=12000, step=1000, key="max_chars",
                                help="Begrenzt den Text, der embedded wird. 12000 Zeichen reichen für Ratgeberseiten und bleiben unter den Token-Limits.")
    st.caption("Immer der jüngste Snapshot mit Status 200. Ohne Snapshot: Fallback aus Anker, Kontext, Titel und URL-Pfad, kein generierter Text.")
    if "recovered_for" in S and S["recovered_for"] != S["ranked"]:
        st.warning("Filter oder Backlinks geändert, Abruf aus der Wayback Machine erneut starten.")
    if st.button("Inhalte aus der Wayback Machine holen",
                 help="Holt je toter URL den jüngsten Snapshot mit Status 200 aus archive.org, etwa zwei bis vier Sekunden pro neuer URL, gecachte URLs sind sofort da."):
        run_wayback()
    if "recovered" in S:
        rec = S["recovered"]
        counts = {src: sum(r.source == src for r in rec) for src in ("wayback", "fallback", "none")}
        errors = sum(bool(r.error) for r in rec)
        st.write(f"Snapshots aus der Wayback Machine: {counts['wayback']} · Fallback aus Ahrefs-Feldern: {counts['fallback']} · Kein Text: {counts['none']} · Fehler: {errors}")
        with st.expander("Rekonstruierte Texte ansehen"):
            for r in rec:
                label = f"**{r.url_to}** · {source_label(r.source)}" + (f" · Snapshot {r.snapshot_timestamp[:8]}" if r.snapshot_timestamp else "")
                label += f" · {r.error}" if r.error else ""
                st.markdown(label)
                st.text((r.text or "(kein Text)")[:600])

# ----------------------------------------------------------------- 4. matching
if "recovered" in S:
    st.header("4. Matching")
    threshold = st.slider("Schwellwert: darunter gilt eine Zeile als Content-Gap", 0.0, 1.0, 0.5, 0.01,
                          help="Beste Ähnlichkeit darunter = Content-Gap. Die Verteilung hängt vom Modell ab, 0.5 ist ein Startwert.")
    match_fallback = st.checkbox("Fallback-Zeilen (ohne Snapshot) ebenfalls matchen", value=True,
                                 help="Zeilen ohne Snapshot in der Wayback Machine werden mit Anker, Kontext, Titel und URL-Pfad gematcht. Ergebnis ist unschärfer, aber oft brauchbar.")
    blocked = "frog" not in S or not dim_valid
    if blocked:
        st.warning("Erst den Frog-Export laden und den Dimensionscheck bestehen.")
    if st.button("Matching starten", disabled=blocked,
                 help="Berechnet Embeddings der rekonstruierten Texte (kostet Tokens beim Anbieter) und ordnet jeder toten URL die ähnlichste eigene Seite zu."):
        run_matching()
    if "vectors" in S:
        params = (threshold, match_fallback)
        if S.get("results_params") != params:
            # a live check result is a fact about the backlink, not about the threshold
            checked = {(r.backlink.url_from, r.backlink.url_to): r.verification for r in S.get("results", [])}
            results = build_results(S["recovered_for"], S["recovered"], S["vectors"], S["frog"].pages,
                                    threshold=threshold, match_fallback=match_fallback)
            for r in results:
                r.verification = checked.get((r.backlink.url_from, r.backlink.url_to), r.verification)
            S["results"] = results
            S["results_params"] = params
            clear_drafts()  # a draft must not describe an outdated top suggestion
        df = results_to_dataframe(S["results"])
        only_gaps = st.checkbox("Nur Content-Gaps zeigen",
                                help="Zeigt nur Zeilen, zu denen keine eigene Seite ausreichend passt. Das sind Themen, für die du neuen Content brauchen könntest.")
        shown = df[df["Content-Gap"] == "Ja"] if only_gaps else df
        st.dataframe(shown.style.apply(lambda row: ["background-color: #ffe5e5" if row["Content-Gap"] == "Ja" else ""] * len(row), axis=1),
                     width="stretch", hide_index=True)

# ----------------------------------------------------------------- 5. verify + outreach
if "results" in S:
    st.header("5. Verifikation und Outreach")
    if st.button("Live prüfen: Ziel noch 404 und Link noch vorhanden?",
                 help="Ruft Ziel-URL und linkgebende Seite auf: ist das Ziel noch 404/410 und steht der Link noch da?"):
        bar = st.progress(0.0)
        with httpx.Client() as client:
            verify_results(S["results"], client, progress=lambda i, n: bar.progress(i / n, text=f"{i}/{n}"), user_agent=agent)
        S["verify_done"] = True
        st.rerun()  # section 4 above already rendered: show the new verification everywhere
    if S.pop("verify_done", False):
        st.success("Verifikation abgeschlossen.")
    df = results_to_dataframe(S["results"])
    c1, c2 = st.columns(2)
    c1.download_button("CSV herunterladen", to_csv_bytes(df), "broken-link-matches.csv", "text/csv",
                       help="Alle Ergebnisse inklusive Vorschlägen, Scores und Verifikation als CSV-Datei.")
    c2.download_button("Excel herunterladen", to_xlsx_bytes(df), "broken-link-matches.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       help="Alle Ergebnisse inklusive Vorschlägen, Scores und Verifikation als Excel-Datei.")
    st.subheader("Mail-Entwürfe")
    sender_missing = not (sender_name and own_domain)
    if key_missing:
        st.caption(KEY_MISSING_HINT)
    elif sender_missing:
        st.caption(SENDER_MISSING_HINT)
    titles = {p.url: p.title for p in S["frog"].pages}
    seen: dict[str, int] = {}
    for r in S["results"]:
        if not r.top:
            continue
        base = hashlib.sha1(f"{r.backlink.url_from}|{r.backlink.url_to}".encode()).hexdigest()[:12]
        n = seen.get(base, 0)
        seen[base] = n + 1
        row_key = base if n == 0 else f"{base}-{n}"  # same page may link the dead URL several times
        dr = f"DR {r.backlink.domain_rating:.0f}" if r.backlink.domain_rating is not None else "DR unbekannt"
        with st.expander(f"#{r.priority} · {dr} · {r.backlink.url_from}"):
            st.write(f"Tote URL: {r.backlink.url_to}")
            st.write(f"Vorschlag: {r.top[0].url} (Score {r.top[0].score:.2f}) · Verifikation: {r.verification}")
            if r.is_content_gap:
                st.caption("Content-Gap: keine ausreichend passende eigene Seite, daher kein Mail-Entwurf.")
            elif st.button("Mail-Entwurf erzeugen", key=f"mail_{row_key}", disabled=key_missing or sender_missing,
                           help="Erzeugt mit dem Chat-Modell einen kurzen Entwurf. Nichts wird versendet."):
                try:
                    S[f"ta_{row_key}"] = draft_mail(
                        r, sender_name, own_domain,
                        provider=provider, model=chat_model, api_key=api_key, base_url=base_url,
                        suggestion_title=titles.get(r.top[0].url, ""),
                    )
                except OutreachError as exc:
                    st.error(str(exc))
            if f"ta_{row_key}" in S:
                st.text_area("Entwurf (editierbar)", key=f"ta_{row_key}", height=220,
                             help="Du kannst den Entwurf hier direkt anpassen. Er wird nicht versendet, kopiere ihn in dein Mailprogramm.")

# ----------------------------------------------------------------- next step + one-click run
with next_step_box:
    if "run_error" in S:  # set by a failed "Los geht's" run before its rerun
        st.error(S.pop("run_error"))
    kind, hint = next_step_hint()
    getattr(st, kind)(hint)
    missing = missing_inputs()
    if st.button("Los geht's", type="primary", key="run_all", disabled=bool(missing),
                 help="Führt Dimensionscheck, Wayback-Machine-Abruf und Matching nacheinander aus. Kostet Embedding-Tokens, "
                      "gecachte Texte und Vektoren werden wiederverwendet."):
        with st.status("Läuft …", expanded=True) as run_status:
            run_error = run_all()
            run_status.update(label="Abgebrochen." if run_error else "Fertig.", state="error" if run_error else "complete")
        if run_error:
            S["run_error"] = f"\"Los geht's\" abgebrochen: {run_error}"
        st.rerun()  # sections 1 to 5 above were rendered before the run
    if missing:
        st.caption("Es fehlt noch: " + ", ".join(missing) + ".")
