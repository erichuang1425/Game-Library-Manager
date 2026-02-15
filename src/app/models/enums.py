"""Enumerated types for game library domain values.

Using (str, Enum) ensures backward compatibility — enum values serialize
as plain strings in JSON, so json_store.py needs no changes.
"""
from enum import Enum


class GameStatus(str, Enum):
    BACKLOG = "backlog"
    PLAYING = "playing"
    FINISHED = "finished"
    DROPPED = "dropped"


class SortMode(str, Enum):
    TITLE = "title"
    LAST_PLAYED = "last_played"
    RATING = "rating"
    LAUNCH_COUNT = "launch_count"
    LAST_CHECKED = "last_checked"


class QuickFilter(str, Enum):
    ALL = "all"
    MISSING = "missing"
    UPDATES = "updates"
    SOURCE = "source"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ShortcutType(str, Enum):
    LNK = "lnk"
    URL = "url"
    HTML = "html"


class ViewMode(str, Enum):
    COMFORTABLE = "comfortable"
    COMPACT = "compact"


class BrowseMode(str, Enum):
    SCROLL = "scroll"
    PAGES = "pages"
