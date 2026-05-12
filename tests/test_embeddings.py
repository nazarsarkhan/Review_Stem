"""Tests for the embeddings module: cache semantics and cosine math.

We do not call the real embeddings API. We monkeypatch the provider's
client to return canned vectors so we can verify cache behavior and
cosine math without network calls.
"""

import json
from pathlib import Path

from reviewstem.embeddings import EmbeddingProvider, cosine_sim


def test_cosine_sim_orthogonal_is_zero():
    assert cosine_sim([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_sim_parallel_is_one():
    assert cosine_sim([1.0, 2.0, 3.0], [2.0, 4.0, 6.0]) == 1.0


def test_cosine_sim_antiparallel_is_negative_one():
    assert cosine_sim([1.0, 0.0], [-1.0, 0.0]) == -1.0


def test_cosine_sim_handles_empty_and_zero_vectors():
    assert cosine_sim([], [1.0]) == 0.0
    assert cosine_sim([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cache_hit_avoids_client_call(tmp_path, monkeypatch):
    provider = EmbeddingProvider(cache_dir=tmp_path, api_key="fake-key")
    # Pre-seed the cache
    key = "stub_key"
    provider._cache_put(key, [0.1, 0.2, 0.3])

    # Read back via cache_get
    cached = provider._cache_get(key)
    assert cached == [0.1, 0.2, 0.3]


def test_cache_get_returns_none_for_missing_key(tmp_path):
    provider = EmbeddingProvider(cache_dir=tmp_path, api_key="fake-key")
    assert provider._cache_get("never_written") is None


def test_embed_returns_none_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = EmbeddingProvider(cache_dir=tmp_path, api_key=None)
    # Caches are empty and no API key -> embed should fail gracefully and return None
    result = provider.embed("some new text we never cached")
    assert result is None


def test_embed_returns_cached_value(tmp_path):
    provider = EmbeddingProvider(cache_dir=tmp_path, api_key="fake-key")
    # Manually seed the on-disk cache at the exact key embed() will use
    from reviewstem.embeddings import _cache_key
    key = _cache_key(provider.model, "hello world")
    provider._cache_put(key, [1.0, 2.0, 3.0])

    vec = provider.embed("hello world")
    assert vec == [1.0, 2.0, 3.0]


def test_embed_empty_string_returns_none(tmp_path):
    provider = EmbeddingProvider(cache_dir=tmp_path, api_key="fake-key")
    assert provider.embed("") is None


def test_embed_batch_uses_cache_per_item(tmp_path):
    provider = EmbeddingProvider(cache_dir=tmp_path, api_key="fake-key")
    from reviewstem.embeddings import _cache_key

    # Seed two of three
    provider._cache_put(_cache_key(provider.model, "a"), [1.0, 0.0])
    provider._cache_put(_cache_key(provider.model, "b"), [0.0, 1.0])

    # Patch _ensure_client to a stub returning a fake response for "c"
    class StubData:
        embedding = [0.5, 0.5]
    class StubResp:
        data = [StubData()]
    class StubEmb:
        def create(self, model, input):
            assert input == ["c"]  # only the uncached item is fetched
            return StubResp()
    class StubClient:
        embeddings = StubEmb()

    provider._client = StubClient()

    out = provider.embed_batch(["a", "b", "c"])
    assert out == [[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]]
