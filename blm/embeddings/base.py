"""Provider-agnostic embedding interface with batching and split-on-error."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import httpx
import numpy as np


class EmbeddingError(Exception):
    pass


class EmbeddingProvider(ABC):
    name: str = "base"
    batch_size: int = 32

    def __init__(self, model: str, client: Optional[httpx.Client] = None):
        self.model = model
        self.client = client or httpx.Client(timeout=60.0)

    @abstractmethod
    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed one batch. Raise EmbeddingError on any failure."""

    def _embed_split(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        try:
            return [np.asarray(v, dtype=np.float32) for v in self._embed_batch(texts)]
        except EmbeddingError as exc:
            if len(texts) == 1:
                return [None]
            if _is_auth_error(exc):
                raise
            mid = len(texts) // 2
            return self._embed_split(texts[:mid]) + self._embed_split(texts[mid:])

    def embed(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        out: list[Optional[np.ndarray]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(self._embed_split(texts[start : start + self.batch_size]))
        return out

    def probe_dimension(self) -> int:
        return len(self._embed_batch(["Dimensionstest"])[0])


def _is_auth_error(exc: Exception) -> bool:
    return "401" in str(exc) or "403" in str(exc)


def raise_for_status(resp: httpx.Response, provider: str) -> None:
    if resp.status_code >= 400:
        raise EmbeddingError(f"{provider}: HTTP {resp.status_code}: {resp.text[:300]}")
