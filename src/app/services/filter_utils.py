"""
Game Filtering Utilities.

Provides reusable filtering, sorting, and search functions for game libraries.
Extracted from main_window.py for better testability and reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from app.models import Game
from app.models.enums import QuickFilter, SortMode
from app.services.version_parser import parse_version, compare_versions, CompareResult


@dataclass
class FilterConfig:
    """Configuration for filtering games."""
    quick_filter: str = QuickFilter.ALL
    status_filter: str = "all"
    confidence_filter: str = "all"
    type_filter: str = "all"
    tag_filter: Optional[str] = None
    search_text: str = ""
    sort_by: str = SortMode.TITLE


class SearchCache:
    """
    Cache for pre-computed search haystacks.

    Improves search performance by caching the haystack strings
    for each game, avoiding repeated string building on every search.

    Usage:
        cache = SearchCache()
        # After loading/modifying games:
        cache.build(games)
        # For searching:
        matches = cache.search(games, "query")
        # After editing a game:
        cache.invalidate(game_id)
    """

    def __init__(self, max_size: int = 10000) -> None:
        """
        Initialize the search cache.

        Args:
            max_size: Maximum number of games to cache (prevents memory issues)
        """
        self._cache: Dict[str, str] = {}  # game_id -> haystack
        self._dirty: Set[str] = set()  # game_ids needing rebuild
        self._max_size = max_size

    def build(self, games: List[Game]) -> None:
        """
        Build/rebuild the cache for a list of games.

        Args:
            games: List of games to cache
        """
        # Clear cache if it would exceed max size
        if len(games) > self._max_size:
            self._cache.clear()
            self._dirty.clear()
            return

        # Remove stale entries
        current_ids = {g.game_id for g in games}
        stale_ids = set(self._cache.keys()) - current_ids
        for game_id in stale_ids:
            del self._cache[game_id]

        # Build haystacks for new/dirty games
        for game in games:
            if game.game_id not in self._cache or game.game_id in self._dirty:
                self._cache[game.game_id] = build_search_haystack(game)
                self._dirty.discard(game.game_id)

    def get_haystack(self, game: Game) -> str:
        """
        Get the cached haystack for a game.

        Args:
            game: The game to get haystack for

        Returns:
            The cached haystack, or builds it if not cached
        """
        if game.game_id in self._dirty or game.game_id not in self._cache:
            self._cache[game.game_id] = build_search_haystack(game)
            self._dirty.discard(game.game_id)
        return self._cache[game.game_id]

    def invalidate(self, game_id: str) -> None:
        """
        Mark a game's cache entry as needing rebuild.

        Call this after modifying a game's searchable fields.

        Args:
            game_id: The ID of the modified game
        """
        self._dirty.add(game_id)

    def invalidate_all(self) -> None:
        """Mark all entries as needing rebuild."""
        self._dirty.update(self._cache.keys())

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()
        self._dirty.clear()

    def search(self, games: List[Game], query: str) -> List[Game]:
        """
        Search games using cached haystacks.

        Args:
            games: List of games to search
            query: Search query (will be lowercased)

        Returns:
            List of games matching the query
        """
        if not query:
            return games

        query_lower = query.strip().lower()
        if not query_lower:
            return games

        return [g for g in games if query_lower in self.get_haystack(g)]

    @property
    def size(self) -> int:
        """Return the number of cached entries."""
        return len(self._cache)

    @property
    def dirty_count(self) -> int:
        """Return the number of dirty entries."""
        return len(self._dirty)


# Global search cache instance
_search_cache: Optional[SearchCache] = None


def get_search_cache() -> SearchCache:
    """Get the global search cache instance."""
    global _search_cache
    if _search_cache is None:
        _search_cache = SearchCache()
    return _search_cache


def is_game_missing(game: Game) -> bool:
    """
    Check if a game's shortcut or related files are missing.

    Args:
        game: The game to check

    Returns:
        True if any required files are missing
    """
    # Check main shortcut path
    if game.shortcut_path:
        shortcut_path = Path(game.shortcut_path)
        if not shortcut_path.exists():
            return True
    else:
        return True

    # For .lnk files, check if the target exists
    if game.shortcut_type == "lnk" and game.backup_target_path:
        if not Path(game.backup_target_path).exists():
            return True

    # Check archive folder
    if game.archive_folder_path and not Path(game.archive_folder_path).exists():
        return True

    # Check compressed archive
    if game.compressed_archive_path and not Path(game.compressed_archive_path).exists():
        return True

    return False


def game_needs_update(game: Game) -> bool:
    """
    Check if a game has an available update.

    Compares installed version with source version.

    Args:
        game: The game to check

    Returns:
        True if source version is newer than installed version
    """
    if not game.installed_version_raw or not game.source_version_raw:
        return False

    inst_vi = parse_version(game.installed_version_raw)
    src_vi = parse_version(game.source_version_raw)

    if inst_vi is None or src_vi is None:
        return False

    cmp = compare_versions(inst_vi, src_vi)
    return cmp == CompareResult.OLDER


def build_search_haystack(game: Game) -> str:
    """
    Build a searchable string from game fields.

    Combines all searchable fields into a single lowercase string.

    Args:
        game: The game to build haystack for

    Returns:
        Lowercase string containing all searchable content
    """
    parts = [
        game.title,
        game.status,
        game.shortcut_type or "",
        game.confidence,
        " ".join(game.tags),
        game.notes or "",
        game.shortcut_path or "",
        game.backup_target_path or "",
        game.source_url or "",
        game.installed_version_raw or "",
        game.source_version_raw or "",
        game.source_version_num or "",
        game.source_version_suffix or "",
        game.archive_folder_path or "",
        game.compressed_archive_path or "",
    ]
    return " ".join(parts).lower()


def match_search(game: Game, query: str) -> bool:
    """
    Check if a game matches a search query.

    Args:
        game: The game to check
        query: Lowercase search query

    Returns:
        True if game matches the query
    """
    if not query:
        return True

    haystack = build_search_haystack(game)
    return query in haystack


def apply_quick_filter(games: List[Game], quick_filter: str) -> List[Game]:
    """
    Apply quick filter to a list of games.

    Args:
        games: List of games to filter
        quick_filter: "all", "missing", "updates", or "source"

    Returns:
        Filtered list of games
    """
    if quick_filter == QuickFilter.ALL:
        return games
    elif quick_filter == QuickFilter.MISSING:
        return [g for g in games if is_game_missing(g)]
    elif quick_filter == QuickFilter.UPDATES:
        return [g for g in games if game_needs_update(g)]
    elif quick_filter == QuickFilter.SOURCE:
        return [g for g in games if g.source_url]
    return games


def apply_dropdown_filters(
    games: List[Game],
    status_filter: str = "all",
    confidence_filter: str = "all",
    type_filter: str = "all",
    tag_filter: Optional[str] = None,
) -> List[Game]:
    """
    Apply dropdown filters to a list of games.

    Args:
        games: List of games to filter
        status_filter: Status filter value
        confidence_filter: Confidence filter value
        type_filter: Shortcut type filter value
        tag_filter: Optional tag filter

    Returns:
        Filtered list of games
    """
    result = games

    if status_filter != "all":
        result = [g for g in result if g.status == status_filter]

    if confidence_filter != "all":
        result = [g for g in result if g.confidence == confidence_filter]

    if type_filter != "all":
        result = [g for g in result if (g.shortcut_type or "") == type_filter]

    if tag_filter:
        tag_lower = tag_filter.lower()
        result = [g for g in result if any(t.lower() == tag_lower for t in g.tags)]

    return result


def apply_search_filter(games: List[Game], search_text: str) -> List[Game]:
    """
    Apply search text filter to a list of games.

    Args:
        games: List of games to filter
        search_text: Search query text

    Returns:
        Filtered list of games
    """
    query = search_text.strip().lower()
    if not query:
        return games

    return [g for g in games if match_search(g, query)]


def sort_games(games: List[Game], sort_by: str) -> List[Game]:
    """
    Sort a list of games by the specified criterion.

    Args:
        games: List of games to sort
        sort_by: Sort criterion ("title", "last_played", "rating", "launch_count", "last_checked")

    Returns:
        Sorted list of games
    """
    if sort_by == SortMode.LAST_PLAYED:
        return sorted(games, key=lambda g: g.last_played or datetime.min, reverse=True)
    elif sort_by == SortMode.RATING:
        return sorted(games, key=lambda g: g.rating if g.rating is not None else -1, reverse=True)
    elif sort_by == SortMode.LAUNCH_COUNT:
        return sorted(games, key=lambda g: g.launch_count or 0, reverse=True)
    elif sort_by == SortMode.LAST_CHECKED:
        return sorted(games, key=lambda g: g.source_checked_at or datetime.min, reverse=True)
    else:
        return sorted(games, key=lambda g: g.title.lower())


def filter_and_sort_games(
    games: List[Game],
    config: FilterConfig,
) -> List[Game]:
    """
    Apply all filters and sorting to a list of games.

    This is the main entry point for filtering the game library.

    Args:
        games: Full list of games to filter
        config: Filter configuration

    Returns:
        Filtered and sorted list of games
    """
    result = games

    # Apply quick filter
    result = apply_quick_filter(result, config.quick_filter)

    # Apply dropdown filters
    result = apply_dropdown_filters(
        result,
        status_filter=config.status_filter,
        confidence_filter=config.confidence_filter,
        type_filter=config.type_filter,
        tag_filter=config.tag_filter,
    )

    # Apply search filter
    result = apply_search_filter(result, config.search_text)

    # Sort results
    result = sort_games(result, config.sort_by)

    return result


def count_quick_filter_matches(games: List[Game]) -> dict:
    """
    Count games matching each quick filter.

    Args:
        games: List of games to count

    Returns:
        Dict with counts for "all", "missing", "updates", "source"
    """
    return {
        "all": len(games),
        "missing": sum(1 for g in games if is_game_missing(g)),
        "updates": sum(1 for g in games if game_needs_update(g)),
        "source": sum(1 for g in games if g.source_url),
    }
