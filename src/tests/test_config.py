"""Tests for config.py — AppConfig dataclass."""
import json
import pytest
from pathlib import Path
from unittest.mock import patch
from app.config import AppConfig


class TestAppConfigDefaults:
    def test_default_values(self):
        cfg = AppConfig()
        assert cfg.root_folder == ""
        assert cfg.view_mode == "comfortable"
        assert cfg.focus_mode is False
        assert cfg.quick_filter == "all"
        assert cfg.tag_filter is None
        assert cfg.status_filter == "all"
        assert cfg.sort_by == "title"
        assert cfg.theme == "dark"
        assert cfg.font_family == "Segoe UI"
        assert cfg.details_on_selection is True
        assert cfg.splitter_sizes is None


class TestAppConfigUpdate:
    def test_update_single_field(self):
        cfg = AppConfig()
        cfg.update(theme="light")
        assert cfg.theme == "light"

    def test_update_multiple_fields(self):
        cfg = AppConfig()
        cfg.update(theme="light", view_mode="compact", focus_mode=True)
        assert cfg.theme == "light"
        assert cfg.view_mode == "compact"
        assert cfg.focus_mode is True

    def test_update_ignores_unknown_fields(self):
        cfg = AppConfig()
        cfg.update(nonexistent="value")
        assert not hasattr(cfg, "nonexistent") or cfg._extra.get("nonexistent") is None


class TestAppConfigDictCompat:
    def test_get_known_field(self):
        cfg = AppConfig(theme="light")
        assert cfg.get("theme") == "light"

    def test_get_with_default(self):
        cfg = AppConfig()
        assert cfg.get("nonexistent", "fallback") == "fallback"

    def test_setitem_known_field(self):
        cfg = AppConfig()
        cfg["theme"] = "light"
        assert cfg.theme == "light"

    def test_setitem_unknown_field(self):
        cfg = AppConfig()
        cfg["custom_theme"] = {"bg": "#000"}
        assert cfg._extra["custom_theme"] == {"bg": "#000"}

    def test_contains_known(self):
        cfg = AppConfig()
        assert "theme" in cfg

    def test_contains_extra(self):
        cfg = AppConfig()
        cfg._extra["custom_theme"] = {}
        assert "custom_theme" in cfg

    def test_contains_missing(self):
        cfg = AppConfig()
        assert "nonexistent" not in cfg


class TestAppConfigSerialization:
    def test_to_dict(self):
        cfg = AppConfig(theme="light")
        cfg._extra["custom_key"] = "value"
        d = cfg.to_dict()
        assert d["theme"] == "light"
        assert d["custom_key"] == "value"
        assert "_extra" not in d

    def test_load_from_dict(self):
        raw = {"theme": "light", "focus_mode": True, "custom_stuff": 42}
        with patch("app.config.load_settings", return_value=raw):
            cfg = AppConfig.load()
        assert cfg.theme == "light"
        assert cfg.focus_mode is True
        assert cfg._extra["custom_stuff"] == 42

    def test_save_preserves_extra(self):
        saved = {}
        def mock_save(path, data):
            saved.update(data)

        cfg = AppConfig(theme="light")
        cfg._extra["custom_key"] = "preserved"
        with patch("app.config.save_settings", mock_save):
            cfg.save()

        assert saved["theme"] == "light"
        assert saved["custom_key"] == "preserved"
        assert "_extra" not in saved
