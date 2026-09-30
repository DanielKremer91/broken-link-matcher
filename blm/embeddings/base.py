"""Provider-agnostic embedding interface with batching and split-on-error."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import httpx
import numpy as np


# HTTP statuses that indicate a problem with the input itself (splittable).
_PER_INPUT_STATUSES = frozenset({400, 413, 422})


class EmbeddingError(Exception):
    """Embedding failure. ``fatal`` errors abort the run instead of being split."""

    def __init__(self, message: str, status: Optional[int] = None, fatal: bool = True):
        super().__init__(message)
        self.status = status
        self.fatal = fatal


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
            if exc.fatal:
                raise
            if len(texts) == 1:
                return [None]
            mid = len(texts) // 2
            return self._embed_split(texts[:mid]) + self._embed_split(texts[mid:])

    def embed(self, texts: list[str]) -> list[Optional[np.ndarray]]:
        out: list[Optional[np.ndarray]] = []
        for start in range(0, len(texts), self.batch_size):
            out.extend(self._embed_split(texts[start : start + self.batch_size]))
        return out

    def probe_dimension(self) -> int:
        vectors = self._embed_batch(["Dimensionstest"])
        if not vectors:
            raise EmbeddingError(f"{self.name}: empty response", fatal=True)
        return len(vectors[0])


def raise_for_status(resp: httpx.Response, provider: str) -> None:
    """Raise EmbeddingError for HTTP errors; only per-input statuses are splittable."""
    status = resp.status_code
    if status < 400:
        return
    body = resp.text[:300]
    fatal = status not in _PER_INPUT_STATUSES
    if status == 400 and "api key" in resp.text.lower():
        # Gemini reports an invalid key as HTTP 400.
        fatal = True
    raise EmbeddingError(f"{provider}: HTTP {status}: {body}", status=status, fatal=fatal)


def malformed_response(provider: str) -> EmbeddingError:
    return EmbeddingError(f"{provider}: malformed response", fatal=True)


def check_vector_count(vectors: list, texts: list[str], provider: str) -> list:
    """Ensure the provider returned exactly one vector per input text."""
    if len(vectors) != len(texts):
        raise EmbeddingError(f"{provider}: response length mismatch", fatal=True)
    return vectors
