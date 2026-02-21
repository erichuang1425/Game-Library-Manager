"""
Game Grid Package.

Provides widgets for displaying games in a grid layout.

Classes:
    GameGrid: Container widget for displaying game cards in a responsive grid
    GameCard: Interactive card widget for individual games
    SkeletonCard: Placeholder card shown during loading

Functions:
    status_label: Convert status code to display label
    confidence_icon: Get emoji icon for confidence level
    stars: Convert rating to star display
    relative_time: Convert datetime to relative time string
"""

from .grid import GameGrid
from .card import GameCard
from .skeleton import SkeletonCard
from .display_utils import status_label, confidence_icon, stars, relative_time

__all__ = [
    "GameGrid",
    "GameCard",
    "SkeletonCard",
    "status_label",
    "confidence_icon",
    "stars",
    "relative_time",
]
