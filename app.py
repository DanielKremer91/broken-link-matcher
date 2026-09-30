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
    st.dataframe(preview, width="stretch", hide_index=True)

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
        shown = df[df["Content-Gap"] == "Ja"] if only_gaps else df
        st.dataframe(shown.style.apply(lambda row: ["background-color: #ffe5e5" if row["Content-Gap"] == "Ja" else ""] * len(row), axis=1),
                     width="stretch", hide_index=True)

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
