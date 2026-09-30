from __future__ import annotations

from typing import Optional

import httpx

from blm.embeddings.base import EmbeddingError, EmbeddingProvider, raise_for_status

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaEmbeddings(EmbeddingProvider):
    name = "ollama"
    batch_size = 16

    def __init__(self, model: str, base_url: Optional[str] = None, client: Optional[httpx.Client] = None):
        super().__init__(model, client)
        self.base_url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/")

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self.client.post(f"{self.base_url}/api/embed", json={"model": self.model, "input": texts})
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"ollama: {exc}") from exc
        raise_for_status(resp, "ollama")
        return resp.json()["embeddings"]
