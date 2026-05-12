"""Embedding-based similarity for the Epigenetics fallback retrieval.

When OpenSpace MCP is unavailable, Epigenetics falls back to in-process
retrieval. The original scorer was pure term matching against skill fields.
That misses semantic matches (a diff that mentions `redis` but is really
about namespace mismatches still pulls the generic Cache Coherence skill).

This module provides a sync embedding provider with an on-disk cache so
embeddings are computed once and reused across runs. The Epigenetics
scorer combines a 0.7 weight on cosine similarity with a 0.3 weight on
the existing term score, preserving interpretability (term hits still
become retrieval reasons in the trace).

If `OPENAI_API_KEY` is missing or the embeddings call fails, the provider
returns None and Epigenetics falls back to pure term matching. This makes
the embedding upgrade opt-in: airgapped runs still work.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Sequence

from .logger import logger

DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"


def _cache_key(model: str, text: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


def cosine_sim(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity in [-1, 1]. Returns 0 if either vector is degenerate."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


class EmbeddingProvider:
    """Sync OpenAI embeddings client with an on-disk JSON cache.

    The cache is keyed by sha256(model:text) and persists across runs, so
    embedding a skill catalog is paid once and the cost amortizes over every
    future benchmark or review.
    """

    def __init__(
        self,
        model: str = DEFAULT_EMBEDDING_MODEL,
        cache_dir: Path | str = ".reviewstem/embeddings",
        api_key: str | None = None,
    ):
        self.model = model
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._client = None  # lazy

    def _ensure_client(self):
        if self._client is not None:
            return self._client
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set; embeddings disabled.")
        import openai  # local import keeps offline runs fast
        self._client = openai.OpenAI(api_key=self.api_key)
        return self._client

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _cache_get(self, key: str) -> list[float] | None:
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Embedding cache miss for %s: %s", key[:8], e)
            return None

    def _cache_put(self, key: str, vec: list[float]) -> None:
        self._cache_path(key).write_text(json.dumps(vec), encoding="utf-8")

    def embed(self, text: str) -> list[float] | None:
        """Embed a single string. Returns None on failure (caller falls back)."""
        if not text:
            return None
        key = _cache_key(self.model, text)
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        try:
            client = self._ensure_client()
            response = client.embeddings.create(model=self.model, input=[text])
            vec = list(response.data[0].embedding)
            self._cache_put(key, vec)
            return vec
        except Exception as e:
            logger.warning("Embedding call failed (falling back to term-only): %s", e)
            return None

    def embed_batch(self, texts: Sequence[str]) -> list[list[float] | None]:
        """Embed many strings. Cache hits do not count against the API call."""
        results: list[list[float] | None] = [None] * len(texts)
        to_fetch: list[tuple[int, str]] = []

        for i, text in enumerate(texts):
            if not text:
                continue
            key = _cache_key(self.model, text)
            cached = self._cache_get(key)
            if cached is not None:
                results[i] = cached
            else:
                to_fetch.append((i, text))

        if not to_fetch:
            return results

        try:
            client = self._ensure_client()
            response = client.embeddings.create(
                model=self.model,
                input=[text for _, text in to_fetch],
            )
            for (idx, text), entry in zip(to_fetch, response.data):
                vec = list(entry.embedding)
                self._cache_put(_cache_key(self.model, text), vec)
                results[idx] = vec
        except Exception as e:
            logger.warning("Batch embedding call failed (falling back): %s", e)

        return results
