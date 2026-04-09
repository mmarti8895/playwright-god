"""Unit tests for playwright_god.embedder."""

from __future__ import annotations

import math

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
        result = self.embedder(["normalised vector test"])[0]
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
