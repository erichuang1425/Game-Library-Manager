"""
Test configuration - mock platform-specific modules unavailable on Linux CI.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock

# Mock Windows-only modules before any app imports
for mod_name in [
    "pythoncom",
    "win32com",
    "win32com.shell",
    "win32com.shell.shell",
    "winreg",
    "PySide6",
    "PySide6.QtWidgets",
    "PySide6.QtCore",
    "PySide6.QtGui",
]:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

import pytest
from app.models import Game


@pytest.fixture
def sample_game():
    """A single test game with common fields populated."""
    return Game(game_id="test-1", title="Test Game", status="backlog")


@pytest.fixture
def sample_games():
    """A small list of test games covering different statuses and tags."""
    return [
        Game(
            game_id="1",
            title="Alpha Game",
            status="playing",
            rating=8,
            tags=["rpg"],
            source_url="https://example.com/alpha",
            confidence="high",
            shortcut_type="lnk",
        ),
        Game(
            game_id="2",
            title="Beta Game",
            status="backlog",
            rating=None,
            tags=["action"],
            confidence="medium",
            shortcut_type="url",
        ),
        Game(
            game_id="3",
            title="Gamma Game",
            status="finished",
            rating=9,
            tags=["rpg", "action"],
            source_url="https://example.com/gamma",
            confidence="low",
            shortcut_type="html",
        ),
    ]
