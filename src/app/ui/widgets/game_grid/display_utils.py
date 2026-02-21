"""
Display utilities for game grid widgets.

Helper functions for formatting and displaying game information.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional


def status_label(status: str) -> str:
    """Convert status code to display label."""
    mapping = {
        "backlog": "Backlog",
        "playing": "Playing",
        "finished": "Finished",
        "dropped": "Dropped",
    }
    return mapping.get(status, status)


def confidence_icon(conf: str) -> str:
    """Get emoji icon for confidence level."""
    return {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(conf, "🟡")


def stars(rating: Optional[int]) -> str:
    """Convert numeric rating (1-10) to 5-star visual display."""
    if rating is None:
        return "—"
    five = max(1, min(5, round(rating / 2)))
    return "★" * five + "☆" * (5 - five)


def relative_time(dt: Optional[datetime]) -> str:
    """Convert datetime to human-readable relative time."""
    if dt is None:
        return ""

    now = datetime.now()
    diff = now - dt

    seconds = diff.total_seconds()
    if seconds < 0:
        return "just now"

    minutes = seconds / 60
    hours = minutes / 60
    days = hours / 24
    weeks = days / 7
    months = days / 30

    if seconds < 60:
        return "just now"
    elif minutes < 60:
        m = int(minutes)
        return f"{m}m ago"
    elif hours < 24:
        h = int(hours)
        return f"{h}h ago"
    elif days < 7:
        d = int(days)
        return f"{d}d ago"
    elif weeks < 4:
        w = int(weeks)
        return f"{w}w ago"
    elif months < 12:
        m = int(months)
        return f"{m}mo ago"
    else:
        return dt.strftime("%b %Y")
