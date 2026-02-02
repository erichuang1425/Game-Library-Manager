"""
Title matching utilities for fuzzy game matching.

This module provides centralized title normalization and similarity calculation
for matching game titles across the application (bulk import, archive matching, etc.).
"""

from __future__ import annotations

import re
from collections import defaultdict
from functools import lru_cache
from typing import Dict, FrozenSet, List, Optional, Set, TypeVar

from app.logging_utils import get_logger

_log = get_logger("title_matcher")


# ============================================================================
# Title Normalization
# ============================================================================

@lru_cache(maxsize=8192)
def normalize_title(title: str) -> str:
    """
    Normalize a game title for comparison.

    Performs the following transformations:
    - Lowercase
    - Remove URLs
    - Remove version patterns (v1.0, build 123, season 2, etc.)
    - Remove common suffixes (alpha, beta, demo, redux, patreon)
    - Remove numbers
    - Normalize whitespace

    Args:
        title: The original game title

    Returns:
        Normalized title string
    """
    txt = title.lower()

    # Remove URLs
    txt = re.sub(r"https?://[^\s]+", "", txt)

    # Remove path/query components
    txt = re.sub(r"[/#?].*", "", txt)

    # Normalize separators to spaces
    txt = re.sub(r"[._-]+", " ", txt)

    # Remove version patterns
    txt = re.sub(r"\b(v|ver|version|build|b|r|rev|season|s|ep|episode)\s*\.?\s*\d+[.\d]*[a-z]?", "", txt)

    # Remove bracketed content (often contains version, author, etc.)
    txt = re.sub(r"\[.*?\]|\(.*?\)", "", txt)

    # Remove common suffixes
    txt = re.sub(r"\b(alpha|beta|demo|redux|patreon|final|complete|full|steam|gog)\b", "", txt)

    # Remove standalone numbers
    txt = re.sub(r"\b\d+\b", "", txt)

    # Normalize whitespace
    txt = re.sub(r"\s+", " ", txt).strip()

    return txt


@lru_cache(maxsize=8192)
def tokenize(text: str) -> FrozenSet[str]:
    """
    Convert text to a frozenset of tokens for comparison.

    Args:
        text: Text to tokenize (will be normalized first)

    Returns:
        Frozenset of non-empty tokens
    """
    normalized = normalize_title(text)
    return frozenset(t for t in normalized.split() if t and len(t) > 1)


def clear_cache() -> None:
    """Clear the LRU caches for normalize_title and tokenize."""
    normalize_title.cache_clear()
    tokenize.cache_clear()


# ============================================================================
# Similarity Calculation
# ============================================================================

def calculate_similarity(title1: str, title2: str) -> float:
    """
    Calculate Jaccard similarity between two titles.

    The Jaccard similarity is the size of the intersection divided by
    the size of the union of the token sets.

    Args:
        title1: First title to compare
        title2: Second title to compare

    Returns:
        Similarity score between 0.0 (no match) and 1.0 (perfect match)
    """
    tokens1 = tokenize(title1)
    tokens2 = tokenize(title2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = len(tokens1 & tokens2)
    union = len(tokens1 | tokens2)

    return intersection / union if union > 0 else 0.0


def find_best_match(
    query: str,
    candidates: List[str],
    threshold: float = 0.5,
) -> Optional[tuple[str, float]]:
    """
    Find the best matching title from a list of candidates.

    Args:
        query: The title to match
        candidates: List of candidate titles to compare against
        threshold: Minimum similarity score to consider a match

    Returns:
        Tuple of (best_match, score) if a match is found, None otherwise
    """
    best_match = None
    best_score = threshold

    for candidate in candidates:
        score = calculate_similarity(query, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_match is not None:
        return best_match, best_score
    return None


# ============================================================================
# Efficient Batch Matching with Index
# ============================================================================

T = TypeVar("T")


class TitleIndex:
    """
    Efficient index for fuzzy title matching.

    Pre-indexes titles by their tokens for faster lookups compared
    to O(n) scanning. Reduces complexity from O(queries * library)
    to O(queries * average_candidates) where average_candidates << library.
    """

    def __init__(self) -> None:
        self._index: Dict[str, List[tuple[str, object]]] = defaultdict(list)
        self._all_items: List[tuple[str, object]] = []

    def add(self, title: str, item: object) -> None:
        """
        Add a title and its associated item to the index.

        Args:
            title: The title to index
            item: Any associated object (e.g., Game instance)
        """
        tokens = tokenize(title)
        entry = (title, item)
        self._all_items.append(entry)

        for token in tokens:
            self._index[token].append(entry)

    def add_many(self, items: List[tuple[str, object]]) -> None:
        """
        Add multiple title-item pairs to the index.

        Args:
            items: List of (title, item) tuples
        """
        for title, item in items:
            self.add(title, item)

    def find_match(
        self,
        query: str,
        threshold: float = 0.5,
    ) -> Optional[tuple[str, object, float]]:
        """
        Find the best matching item for a query.

        Uses the token index to reduce the number of comparisons.

        Args:
            query: Title to search for
            threshold: Minimum similarity score

        Returns:
            Tuple of (matched_title, item, score) if found, None otherwise
        """
        query_tokens = tokenize(query)

        if not query_tokens:
            return None

        # Collect candidates that share at least one token
        candidates: Set[tuple[str, object]] = set()
        for token in query_tokens:
            candidates.update(self._index.get(token, []))

        if not candidates:
            return None

        # Score candidates
        best_match = None
        best_item = None
        best_score = threshold

        for title, item in candidates:
            score = calculate_similarity(query, title)
            if score > best_score:
                best_score = score
                best_match = title
                best_item = item

        if best_match is not None:
            return best_match, best_item, best_score
        return None

    def find_all_matches(
        self,
        query: str,
        threshold: float = 0.5,
        limit: int = 10,
    ) -> List[tuple[str, object, float]]:
        """
        Find all matching items above the threshold.

        Args:
            query: Title to search for
            threshold: Minimum similarity score
            limit: Maximum number of results

        Returns:
            List of (title, item, score) tuples, sorted by score descending
        """
        query_tokens = tokenize(query)

        if not query_tokens:
            return []

        # Collect candidates
        candidates: Set[tuple[str, object]] = set()
        for token in query_tokens:
            candidates.update(self._index.get(token, []))

        # Score and filter candidates
        matches = []
        for title, item in candidates:
            score = calculate_similarity(query, title)
            if score >= threshold:
                matches.append((title, item, score))

        # Sort by score descending
        matches.sort(key=lambda x: x[2], reverse=True)

        return matches[:limit]

    def clear(self) -> None:
        """Clear the index."""
        self._index.clear()
        self._all_items.clear()

    def __len__(self) -> int:
        """Return the number of indexed items."""
        return len(self._all_items)


# ============================================================================
# Convenience Functions
# ============================================================================

def create_game_index(games: List[object]) -> TitleIndex:
    """
    Create a TitleIndex from a list of Game objects.

    Assumes games have a 'title' attribute.

    Args:
        games: List of Game objects with 'title' attribute

    Returns:
        Configured TitleIndex
    """
    index = TitleIndex()
    for game in games:
        title = getattr(game, "title", None) or getattr(game, "name", None)
        if title:
            index.add(title, game)
    return index


def batch_match(
    queries: List[str],
    library_titles: List[str],
    threshold: float = 0.5,
) -> Dict[str, Optional[tuple[str, float]]]:
    """
    Match multiple queries against a library of titles.

    More efficient than calling find_best_match repeatedly
    because it builds an index first.

    Args:
        queries: List of titles to match
        library_titles: List of library titles to match against
        threshold: Minimum similarity score

    Returns:
        Dict mapping each query to (matched_title, score) or None
    """
    # Build index
    index = TitleIndex()
    for title in library_titles:
        index.add(title, title)

    # Match each query
    results: Dict[str, Optional[tuple[str, float]]] = {}
    for query in queries:
        match = index.find_match(query, threshold)
        if match:
            title, _, score = match
            results[query] = (title, score)
        else:
            results[query] = None

    return results
