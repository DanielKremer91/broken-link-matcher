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
def test_400_is_splittable_and_single_failure_becomes_none():
    calls = []

    def handler(request):
        import json
        inputs = json.loads(request.content)["input"]
        calls.append(len(inputs))
        if "BAD" in inputs:
            return httpx.Response(400, json={"error": "too long"})
        return httpx.Response(200, json={"data": [{"index": i, "embedding": [float(len(t))]} for i, t in enumerate(inputs)]})

    respx.post(OPENAI_URL).mock(side_effect=handler)
    p = make_provider("openai", "m", api_key="k")
    p.batch_size = 2
    vecs = p.embed(["a", "BAD", "ccc"])
    assert calls == [2, 1, 1, 1]  # batch of two, split into singles, then the last batch
    assert vecs[0].tolist() == [1.0]
    assert vecs[1] is None
    assert vecs[2].tolist() == [3.0]


@respx.mock
def test_401_during_embed_raises_immediately_without_split():
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    p = make_provider("openai", "m", api_key="wrong")
    with pytest.raises(EmbeddingError):
        p.embed(["a", "b"])
    assert route.call_count == 1


@respx.mock
def test_single_text_auth_error_raises_not_none():
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(403, json={"error": "forbidden"}))
    p = make_provider("openai", "m", api_key="k")
    with pytest.raises(EmbeddingError):
        p.embed(["x"])


@pytest.mark.parametrize("status", [404, 429, 500, 503])
@respx.mock
def test_429_and_500_are_fatal(status):
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(status, json={"error": "nope"}))
    p = make_provider("openai", "m", api_key="k")
    with pytest.raises(EmbeddingError) as info:
        p.embed(["a", "b"])
    assert info.value.fatal and info.value.status == status
    assert route.call_count == 1


@respx.mock
def test_gemini_400_api_key_invalid_is_fatal():
    route = respx.post(GEMINI_URL).mock(return_value=httpx.Response(400, json={"error": {
        "code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}))
    p = make_provider("gemini", "gemini-embedding-001", api_key="bad")
    with pytest.raises(EmbeddingError):
        p.embed(["a", "b"])
    assert route.call_count == 1


@respx.mock
def test_malformed_response_is_fatal():
    route = respx.post(OPENAI_URL).mock(return_value=httpx.Response(200, json={"foo": 1}))
    p = make_provider("openai", "m", api_key="k")
    with pytest.raises(EmbeddingError, match="malformed"):
        p.embed(["a", "b"])
    assert route.call_count == 1


@respx.mock
def test_length_mismatch_is_fatal():
    respx.post(OLLAMA_URL).mock(return_value=httpx.Response(200, json={"embeddings": [[0.5, 0.5]]}))
    p = make_provider("ollama", "nomic-embed-text")
    with pytest.raises(EmbeddingError, match="length mismatch"):
        p.embed(["a", "b"])


@respx.mock
def test_transport_error_is_fatal():
    route = respx.post(OPENAI_URL).mock(side_effect=httpx.ConnectError("refused"))
    p = make_provider("openai", "m", api_key="k")
    with pytest.raises(EmbeddingError):
        p.embed(["a", "b"])
    assert route.call_count == 1


@respx.mock
def test_auth_error_raises_embedding_error_immediately():
    respx.post(OPENAI_URL).mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    p = make_provider("openai", "m", api_key="wrong")
    with pytest.raises(EmbeddingError, match="401"):
        p.probe_dimension()


def test_base_is_abstract():
    with pytest.raises(TypeError):
        EmbeddingProvider("m")  # type: ignore[abstract]


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
