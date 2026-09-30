"""Embedding providers. Pick one that matches the Screaming Frog configuration."""

from __future__ import annotations

from typing import Optional

import httpx

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


__all__ = ["PROVIDERS", "DEFAULT_EMBED_MODELS", "EmbeddingError", "EmbeddingProvider", "make_provider"]
