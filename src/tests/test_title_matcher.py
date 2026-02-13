"""Tests for title_matcher.py — normalization, similarity, and TitleIndex."""
import pytest
from app.services.title_matcher import (
    normalize_title,
    calculate_similarity,
    tokenize,
)


class TestNormalizeTitle:
    def test_lowercase(self):
        assert normalize_title("MY GAME") == "my game"

    def test_strip_version(self):
        result = normalize_title("My Game v0.1.1")
        assert "0.1.1" not in result
        assert "my game" in result

    def test_strip_brackets(self):
        result = normalize_title("My Game [v0.5] (Demo)")
        assert "[" not in result
        assert "(" not in result

    def test_strip_build(self):
        result = normalize_title("My Game build 42")
        assert "42" not in result

    def test_strip_common_suffixes(self):
        result = normalize_title("My Game Demo")
        assert "demo" not in result

    def test_normalize_separators(self):
        result = normalize_title("my_game-title.ext")
        assert "_" not in result
        assert "-" not in result
        assert "." not in result

    def test_strip_url(self):
        result = normalize_title("My Game https://example.com/path")
        assert "example" not in result


class TestCalculateSimilarity:
    def test_identical_titles(self):
        score = calculate_similarity("Test Game", "Test Game")
        assert score == 1.0

    def test_completely_different(self):
        score = calculate_similarity("abc", "xyz")
        assert score == 0.0

    def test_partial_overlap(self):
        score = calculate_similarity("game alpha beta", "game alpha gamma")
        assert 0.0 < score < 1.0

    def test_empty_strings(self):
        score = calculate_similarity("", "")
        # Both empty should have some defined behavior
        assert isinstance(score, float)


class TestTokenize:
    def test_returns_frozenset(self):
        result = tokenize("hello world")
        assert isinstance(result, frozenset)

    def test_tokens_are_words(self):
        result = tokenize("hello world")
        assert "hello" in result
        assert "world" in result
