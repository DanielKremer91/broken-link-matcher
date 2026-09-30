"""Embedding providers. Pick one that matches the Screaming Frog configuration."""

from __future__ import annotations

from typing import Optional

import httpx
import numpy as np

from blm.cache import JsonCache
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


def embed_cached(
    provider: EmbeddingProvider, texts: list[str], cache: Optional[JsonCache]
) -> list[Optional[np.ndarray]]:
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


__all__ = ["PROVIDERS", "DEFAULT_EMBED_MODELS", "EmbeddingError", "EmbeddingProvider", "embed_cached", "make_provider"]
