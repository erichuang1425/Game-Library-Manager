"""Tests for filter_utils.py — core filtering, sorting, and search logic."""
import pytest
from app.models import Game
from app.services.filter_utils import (
    FilterConfig,
    SearchCache,
    apply_quick_filter,
    apply_dropdown_filters,
    sort_games,
    filter_and_sort_games,
    build_search_haystack,
    match_search,
)


class TestApplyQuickFilter:
    def test_all_returns_all(self, sample_games):
        result = apply_quick_filter(sample_games, "all")
        assert len(result) == 3

    def test_source_filters_to_games_with_url(self, sample_games):
        result = apply_quick_filter(sample_games, "source")
        assert len(result) == 2
        assert all(g.source_url for g in result)

    def test_unknown_filter_returns_all(self, sample_games):
        result = apply_quick_filter(sample_games, "nonexistent")
        assert len(result) == 3


class TestApplyDropdownFilters:
    def test_status_filter(self, sample_games):
        result = apply_dropdown_filters(sample_games, status_filter="backlog")
        assert len(result) == 1
        assert result[0].game_id == "2"

    def test_confidence_filter(self, sample_games):
        result = apply_dropdown_filters(sample_games, confidence_filter="high")
        assert len(result) == 1
        assert result[0].game_id == "1"

    def test_type_filter(self, sample_games):
        result = apply_dropdown_filters(sample_games, type_filter="lnk")
        assert len(result) == 1
        assert result[0].game_id == "1"

    def test_tag_filter_case_insensitive(self, sample_games):
        result = apply_dropdown_filters(sample_games, tag_filter="RPG")
        assert len(result) == 2

    def test_all_filters_return_all(self, sample_games):
        result = apply_dropdown_filters(sample_games)
        assert len(result) == 3

    def test_combined_filters(self, sample_games):
        result = apply_dropdown_filters(
            sample_games, status_filter="playing", confidence_filter="high"
        )
        assert len(result) == 1
        assert result[0].game_id == "1"


class TestSortGames:
    def test_sort_by_title(self, sample_games):
        result = sort_games(sample_games, "title")
        assert [g.title for g in result] == ["Alpha Game", "Beta Game", "Gamma Game"]

    def test_sort_by_rating_descending(self, sample_games):
        result = sort_games(sample_games, "rating")
        assert result[0].rating == 9
        assert result[1].rating == 8
        # None rating comes last (mapped to -1)
        assert result[2].rating is None

    def test_sort_by_launch_count(self):
        games = [
            Game(game_id="a", title="A", launch_count=5),
            Game(game_id="b", title="B", launch_count=10),
            Game(game_id="c", title="C", launch_count=0),
        ]
        result = sort_games(games, "launch_count")
        assert [g.launch_count for g in result] == [10, 5, 0]


class TestSearchCache:
    def test_build_and_search(self, sample_games):
        cache = SearchCache()
        cache.build(sample_games)
        assert cache.size == 3

        matches = cache.search(sample_games, "alpha")
        assert len(matches) == 1
        assert matches[0].game_id == "1"

    def test_search_empty_query_returns_all(self, sample_games):
        cache = SearchCache()
        cache.build(sample_games)
        result = cache.search(sample_games, "")
        assert len(result) == 3

    def test_invalidate_and_rebuild(self, sample_games):
        cache = SearchCache()
        cache.build(sample_games)
        assert cache.dirty_count == 0

        cache.invalidate("1")
        assert cache.dirty_count == 1

        # Search still works — dirty entries get rebuilt on access
        matches = cache.search(sample_games, "alpha")
        assert len(matches) == 1

    def test_search_by_tag(self, sample_games):
        cache = SearchCache()
        cache.build(sample_games)
        matches = cache.search(sample_games, "rpg")
        assert len(matches) == 2

    def test_clear(self, sample_games):
        cache = SearchCache()
        cache.build(sample_games)
        cache.clear()
        assert cache.size == 0


class TestFilterAndSortGames:
    def test_full_pipeline(self, sample_games):
        config = FilterConfig(
            quick_filter="all",
            status_filter="all",
            sort_by="title",
        )
        result = filter_and_sort_games(sample_games, config)
        assert len(result) == 3
        assert result[0].title == "Alpha Game"

    def test_filtered_and_sorted(self, sample_games):
        config = FilterConfig(
            status_filter="all",
            tag_filter="rpg",
            sort_by="rating",
        )
        result = filter_and_sort_games(sample_games, config)
        assert len(result) == 2
        assert result[0].rating == 9  # Gamma rated higher


class TestBuildSearchHaystack:
    def test_includes_title(self, sample_game):
        haystack = build_search_haystack(sample_game)
        assert "test game" in haystack

    def test_includes_status(self, sample_game):
        haystack = build_search_haystack(sample_game)
        assert "backlog" in haystack

    def test_includes_tags(self):
        g = Game(game_id="x", title="X", tags=["rpg", "adventure"])
        haystack = build_search_haystack(g)
        assert "rpg" in haystack
        assert "adventure" in haystack


class TestMatchSearch:
    def test_match_by_title(self, sample_game):
        assert match_search(sample_game, "test") is True

    def test_no_match(self, sample_game):
        assert match_search(sample_game, "zzzzzzz") is False

    def test_empty_query_matches_all(self, sample_game):
        assert match_search(sample_game, "") is True
