"""Centralized icon system for consistent iconography across the app.

Uses carefully selected Unicode glyphs that render well across Windows fonts.
All icons are accessed through the AppIcons class to ensure consistency.
"""
from __future__ import annotations


class AppIcons:
    """Centralized icon definitions for the application.

    Icons are chosen for visual clarity at small sizes and consistent
    rendering on Windows with Segoe UI / Segoe UI Symbol.
    """

    # Navigation — distinct, recognizable at 14-18px
    NAV_LIBRARY = "\U0001F3AE"    # Game controller / Library
    NAV_UPDATES = "\U0001F504"    # Counterclockwise arrows / Refresh
    NAV_HEALTH = "\U0001F6E1"     # Shield / Health checks
    NAV_COLLECTION = "\U0001F4C1" # Folder / Collection
    NAV_SMART = "\u2728"          # Sparkles / Smart collection
    NAV_TOOLS = "\u2699\uFE0F"    # Gear / Tools

    # Actions — clear intent at a glance
    ACT_SCAN = "\u25B6"           # Play triangle / Scan
    ACT_PLAY = "\u25B6"           # Play triangle
    ACT_FOLDER = "\U0001F4C2"     # Open folder
    ACT_SEARCH = "\U0001F50D"     # Magnifying glass
    ACT_FILTER = "\U0001F50E"     # Filter / magnifying glass right
    ACT_SETTINGS = "\u2699"       # Gear
    ACT_ADD = "+"                 # Plus
    ACT_REMOVE = "\u2715"         # X mark
    ACT_EDIT = "\u270F\uFE0F"     # Pencil
    ACT_EXPORT = "\u21E5"         # Right arrow / Export
    ACT_IMPORT = "\u21E4"         # Left arrow / Import
    ACT_CLOSE = "\u2715"          # X mark
    ACT_DOWNLOAD = "\u2B07"       # Down arrow / Download

    # Status indicators — semantically distinct
    STS_BACKLOG = "\u25CB"        # Circle outline / Not started
    STS_PLAYING = "\u25B6"        # Play / Active
    STS_FINISHED = "\u2714"       # Heavy checkmark / Done
    STS_DROPPED = "\u2718"        # Heavy X / Dropped
    STS_UPDATE = "\u2B06"         # Up arrow / Update available

    # Feedback — standard signal icons
    FB_SUCCESS = "\u2714"         # Heavy checkmark
    FB_WARNING = "\u26A0"         # Warning triangle
    FB_ERROR = "\u2718"           # Heavy X mark
    FB_INFO = "\u2139"            # Info circle

    # UI elements — chrome & decoration
    UI_CHEVRON_RIGHT = "\u203A"   # Single right angle quote
    UI_CHEVRON_DOWN = "\u2304"    # Down caret
    UI_CHEVRON_LEFT = "\u2039"    # Single left angle quote
    UI_DOTS = "\u22EF"            # Horizontal ellipsis
    UI_STAR_FULL = "\u2605"       # Filled star
    UI_STAR_EMPTY = "\u2606"      # Empty star
    UI_CLOCK = "\U0001F552"       # Clock face 3 o'clock
    UI_TAG = "\U0001F3F7"         # Label / Tag
    UI_PIN = "\U0001F4CC"         # Pin
    UI_DRAG = "\u2630"            # Trigram / drag handle
    UI_EXPAND = "\u25B8"          # Right-pointing triangle (collapsed)
    UI_COLLAPSE = "\u25BE"        # Down-pointing triangle (expanded)

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
