"""Centralized icon system for consistent iconography across the app.

Uses Unicode symbols initially with a clear abstraction for future SVG support.
All icons are accessed through the AppIcons class to ensure consistency.
"""
from __future__ import annotations


class AppIcons:
    """Centralized icon definitions for the application."""

    # Navigation
    NAV_LIBRARY = "\u2302"       # House / Library
    NAV_UPDATES = "\u21BB"       # Clockwise arrows / Refresh
    NAV_HEALTH = "\u2665"        # Heart / Health
    NAV_COLLECTION = "\u25A3"    # Square with fill / Collection
    NAV_SMART = "\u2606"         # Star outline / Smart collection
    NAV_TOOLS = "\u2699"         # Gear / Tools

    # Actions
    ACT_SCAN = "\u25B6"          # Play triangle / Scan
    ACT_PLAY = "\u25B6"          # Play triangle
    ACT_FOLDER = "\u2750"        # Folder
    ACT_SEARCH = "\u2315"        # Search / Magnifying glass
    ACT_FILTER = "\u2A54"        # Filter funnel
    ACT_SETTINGS = "\u2699"      # Gear
    ACT_ADD = "+"                # Plus
    ACT_REMOVE = "\u2715"        # X mark
    ACT_EDIT = "\u270E"          # Pencil
    ACT_EXPORT = "\u21E5"        # Right arrow / Export
    ACT_IMPORT = "\u21E4"        # Left arrow / Import
    ACT_CLOSE = "\u2715"         # X mark

    # Status indicators
    STS_BACKLOG = "\u25CB"       # Circle outline / Not started
    STS_PLAYING = "\u25B6"       # Play / Active
    STS_FINISHED = "\u2713"      # Checkmark / Done
    STS_DROPPED = "\u2715"       # X / Dropped
    STS_UPDATE = "\u2191"        # Up arrow / Update available

    # Feedback
    FB_SUCCESS = "\u2713"        # Checkmark
    FB_WARNING = "\u26A0"        # Warning triangle
    FB_ERROR = "\u2715"          # X mark
    FB_INFO = "\u2139"           # Info circle

    # UI elements
    UI_CHEVRON_RIGHT = "\u203A"  # Single right angle quote
    UI_CHEVRON_DOWN = "\u2304"   # Down caret
    UI_DOTS = "\u22EF"           # Horizontal ellipsis
    UI_STAR_FULL = "\u2605"      # Filled star
    UI_STAR_EMPTY = "\u2606"     # Empty star
    UI_CLOCK = "\u231A"          # Clock / Time
    UI_TAG = "\u2302"            # Tag

    @staticmethod
    def status_icon(status: str) -> str:
        """Get the icon character for a game status."""
        return {
            "backlog": AppIcons.STS_BACKLOG,
            "playing": AppIcons.STS_PLAYING,
            "finished": AppIcons.STS_FINISHED,
            "dropped": AppIcons.STS_DROPPED,
        }.get(status, AppIcons.STS_BACKLOG)

    @staticmethod
    def nav_icon(key: str) -> str:
        """Get the icon character for a navigation item."""
        return {
            "all": AppIcons.NAV_LIBRARY,
            "updates": AppIcons.NAV_UPDATES,
            "health": AppIcons.NAV_HEALTH,
            "tools": AppIcons.NAV_TOOLS,
        }.get(key, AppIcons.NAV_COLLECTION)
