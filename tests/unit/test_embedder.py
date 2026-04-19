"""Unit tests for playwright_god.embedder."""

from __future__ import annotations

import math
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from playwright_god.embedder import EMBEDDING_DIM, EmbeddingFunction, MockEmbedder


class TestMockEmbedder:
    def setup_method(self):
        self.embedder = MockEmbedder()

    def test_returns_list_of_lists(self):
        result = self.embedder(["hello", "world"])
        assert isinstance(result, list)
        assert all(isinstance(v, list) for v in result)

    def test_output_length_matches_input(self):
        texts = ["a", "b", "c", "d"]
        result = self.embedder(texts)
        assert len(result) == len(texts)

    def test_embedding_dimension(self):
        result = self.embedder(["test text"])
        assert len(result[0]) == EMBEDDING_DIM

    def test_deterministic(self):
        r1 = self.embedder(["hello"])[0]
        r2 = self.embedder(["hello"])[0]
        assert r1 == r2

    def test_different_texts_different_embeddings(self):
        r1 = self.embedder(["hello world"])[0]
        r2 = self.embedder(["goodbye world"])[0]
        assert r1 != r2

    def test_same_text_same_embedding(self):
        text = "the quick brown fox"
        r1 = self.embedder([text])[0]
        r2 = self.embedder([text])[0]
        assert r1 == r2

    def test_unit_vector(self):
        result = self.embedder(["normalized vector test"])[0]
        magnitude = math.sqrt(sum(v * v for v in result))
        assert abs(magnitude - 1.0) < 1e-6

    def test_empty_input(self):
        result = self.embedder([])
        assert result == []

    def test_single_char_text(self):
        result = self.embedder(["x"])
        assert len(result[0]) == EMBEDDING_DIM

    def test_long_text(self):
        long_text = "word " * 1000
        result = self.embedder([long_text])
        assert len(result[0]) == EMBEDDING_DIM

    def test_conforms_to_protocol(self):
        embedder = MockEmbedder()
        assert isinstance(embedder, EmbeddingFunction)


# ---------------------------------------------------------------------------
# DefaultEmbedder (chromadb wrapper)
# ---------------------------------------------------------------------------


class TestDefaultEmbedder:
    def test_raises_import_error_when_chromadb_missing(self):
        # Setting the submodule to None makes `from ... import` raise ImportError.
        with patch.dict(
            sys.modules,
            {"chromadb.utils.embedding_functions": None},
        ):
            from playwright_god.embedder import DefaultEmbedder

            with pytest.raises(ImportError, match="pip install chromadb"):
                DefaultEmbedder()

    def test_delegates_to_chromadb_default_embedding_function(self):
        # Build a fake `chromadb.utils.embedding_functions` module exposing a
        # `DefaultEmbeddingFunction` callable that returns a deterministic 2D list.
        fake_module = types.ModuleType("chromadb.utils.embedding_functions")
        fake_fn_instance = MagicMock(return_value=[[0.1, 0.2], [0.3, 0.4]])
        fake_fn_class = MagicMock(return_value=fake_fn_instance)
        fake_module.DefaultEmbeddingFunction = fake_fn_class

        with patch.dict(
            sys.modules,
            {"chromadb.utils.embedding_functions": fake_module},
        ):
            from playwright_god.embedder import DefaultEmbedder

            embedder = DefaultEmbedder()
            result = embedder(["hello", "world"])

        fake_fn_class.assert_called_once_with()
        fake_fn_instance.assert_called_once_with(["hello", "world"])
        assert result == [[0.1, 0.2], [0.3, 0.4]]
        assert isinstance(result, list)
        assert all(isinstance(v, list) for v in result)


# ---------------------------------------------------------------------------
# OpenAIEmbedder
# ---------------------------------------------------------------------------


class TestOpenAIEmbedder:
    def test_raises_import_error_when_openai_missing(self):
        with patch.dict(sys.modules, {"openai": None}):
            from playwright_god.embedder import OpenAIEmbedder

            with pytest.raises(ImportError, match="pip install openai"):
                OpenAIEmbedder()

    def test_reads_api_key_from_environment(self, monkeypatch):
        # Build a fake openai module with an OpenAI client constructor.
        fake_openai = types.ModuleType("openai")
        fake_client = MagicMock()
        fake_openai.OpenAI = MagicMock(return_value=fake_client)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-from-env")

        with patch.dict(sys.modules, {"openai": fake_openai}):
            from playwright_god.embedder import OpenAIEmbedder

            embedder = OpenAIEmbedder()  # no explicit api_key

        # Verify the constructor was called with the env var value
        fake_openai.OpenAI.assert_called_once_with(api_key="sk-test-from-env")
        assert embedder.model == "text-embedding-3-small"
        assert embedder._client is fake_client

    def test_call_forwards_to_embeddings_api(self, monkeypatch):
        # Stub openai client so embeddings.create returns objects with .embedding.
        fake_openai = types.ModuleType("openai")
        fake_client = MagicMock()
        # Each .data item must expose `.embedding`
        item_a = MagicMock()
        item_a.embedding = [1.0, 2.0]
        item_b = MagicMock()
        item_b.embedding = [3.0, 4.0]
        fake_response = MagicMock()
        fake_response.data = [item_a, item_b]
        fake_client.embeddings.create.return_value = fake_response
        fake_openai.OpenAI = MagicMock(return_value=fake_client)

        monkeypatch.setenv("OPENAI_API_KEY", "sk-anything")

        with patch.dict(sys.modules, {"openai": fake_openai}):
            from playwright_god.embedder import OpenAIEmbedder

            embedder = OpenAIEmbedder(model="text-embedding-3-large")
            result = embedder(["a", "b"])

        fake_client.embeddings.create.assert_called_once_with(
            input=["a", "b"],
            model="text-embedding-3-large",
        )
        assert result == [[1.0, 2.0], [3.0, 4.0]]
