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
