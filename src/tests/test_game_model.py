"""Tests for Game model — defaults, equality, and enum integration."""
import pytest
from app.models import Game
from app.models.enums import GameStatus, Confidence


class TestGameDefaults:
    def test_default_status_is_backlog(self):
        g = Game(game_id="1", title="Test")
        assert g.status == "backlog"
        assert g.status == GameStatus.BACKLOG

    def test_default_confidence_is_medium(self):
        g = Game(game_id="1", title="Test")
        assert g.confidence == "medium"
        assert g.confidence == Confidence.MEDIUM

    def test_default_rating_is_none(self):
        g = Game(game_id="1", title="Test")
        assert g.rating is None

    def test_default_tags_is_empty_list(self):
        g = Game(game_id="1", title="Test")
        assert g.tags == []

    def test_default_launch_count_is_zero(self):
        g = Game(game_id="1", title="Test")
        assert g.launch_count == 0

    def test_default_dominant_color_hex_is_empty(self):
        g = Game(game_id="1", title="Test")
        assert g.dominant_color_hex == ""

    def test_default_icon_upscaled_is_false(self):
        g = Game(game_id="1", title="Test")
        assert g.icon_upscaled is False


class TestGameFields:
    def test_tags_independent_between_instances(self):
        """Ensure default_factory prevents shared mutable state."""
        a = Game(game_id="1", title="A")
        b = Game(game_id="2", title="B")
        a.tags.append("rpg")
        assert b.tags == []

    def test_all_string_fields_default_to_empty(self):
        g = Game(game_id="1", title="Test")
        for field_name in [
            "shortcut_path", "shortcut_type", "backup_target_path",
            "source_url", "installed_version_raw", "source_version_raw",
            "archive_folder_path", "compressed_archive_path",
        ]:
            assert getattr(g, field_name) == "", f"{field_name} should default to ''"


class TestEnumBackwardCompat:
    def test_status_enum_equals_string(self):
        assert GameStatus.BACKLOG == "backlog"
        assert GameStatus.PLAYING == "playing"
        assert GameStatus.FINISHED == "finished"
        assert GameStatus.DROPPED == "dropped"

    def test_confidence_enum_equals_string(self):
        assert Confidence.HIGH == "high"
        assert Confidence.MEDIUM == "medium"
        assert Confidence.LOW == "low"

    def test_game_status_comparison_with_string(self):
        g = Game(game_id="1", title="Test", status=GameStatus.PLAYING)
        assert g.status == "playing"
        assert g.status == GameStatus.PLAYING
