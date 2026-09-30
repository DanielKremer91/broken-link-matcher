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
