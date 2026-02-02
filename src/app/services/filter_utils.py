"""
Game Filtering Utilities.

Provides reusable filtering, sorting, and search functions for game libraries.
Extracted from main_window.py for better testability and reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from app.models import Game
from app.services.version_parser import parse_version, compare_versions, CompareResult


@dataclass
class FilterConfig:
    """Configuration for filtering games."""
    quick_filter: str = "all"  # "all", "missing", "updates", "source"
    status_filter: str = "all"  # "all", "backlog", "playing", "finished", "dropped"
    confidence_filter: str = "all"  # "all", "high", "medium", "low"
    type_filter: str = "all"  # "all", "lnk", "url", "html"
    tag_filter: Optional[str] = None
    search_text: str = ""
    sort_by: str = "title"  # "title", "last_played", "rating", "launch_count", "last_checked"


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
    if quick_filter == "all":
        return games
    elif quick_filter == "missing":
        return [g for g in games if is_game_missing(g)]
    elif quick_filter == "updates":
        return [g for g in games if game_needs_update(g)]
    elif quick_filter == "source":
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
    if sort_by == "last_played":
        return sorted(games, key=lambda g: g.last_played or datetime.min, reverse=True)
    elif sort_by == "rating":
        return sorted(games, key=lambda g: g.rating if g.rating is not None else -1, reverse=True)
    elif sort_by == "launch_count":
        return sorted(games, key=lambda g: g.launch_count or 0, reverse=True)
    elif sort_by == "last_checked":
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
