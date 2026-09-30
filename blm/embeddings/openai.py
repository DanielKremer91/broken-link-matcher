from __future__ import annotations

from typing import Optional

import httpx

from blm.embeddings.base import EmbeddingError, EmbeddingProvider, raise_for_status

OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"


class OpenAIEmbeddings(EmbeddingProvider):
    name = "openai"
    batch_size = 64

    def __init__(self, model: str, api_key: str, client: Optional[httpx.Client] = None):
        super().__init__(model, client)
        if not api_key:
            raise EmbeddingError("openai: API-Schlüssel fehlt")
        self.api_key = api_key

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            resp = self.client.post(
                OPENAI_EMBED_URL,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"model": self.model, "input": texts},
            )
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"openai: {exc}") from exc
        raise_for_status(resp, "openai")
        data = sorted(resp.json()["data"], key=lambda d: d["index"])
        return [d["embedding"] for d in data]
