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
