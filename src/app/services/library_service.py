from __future__ import annotations
from datetime import datetime, timedelta
from typing import List
from app.models import Game

def load_fake_games() -> List[Game]:
    now = datetime.now()
    return [
        Game("1", "Hades", "finished", 9, ["Roguelike", "Action"], now - timedelta(days=12), "exe", "high", "Great combat."),
        Game("2", "Stardew Valley", "playing", 8, ["Co-op", "Chill"], now - timedelta(days=2), "exe", "high", "Play with friends."),
        Game("3", "Celeste", "finished", 9, ["Platformer"], now - timedelta(days=90), "exe", "high", "Hard but fair."),
        Game("4", "Slay the Spire", "backlog", None, ["Deckbuilder", "Roguelike"], None, "exe", "medium", ""),
        Game("5", "Into the Breach", "backlog", None, ["Strategy"], None, "exe", "medium", ""),
        Game("6", "A Short Hike", "finished", 8, ["Chill", "Adventure"], now - timedelta(days=180), "exe", "high", ""),
        Game("7", "Factorio", "playing", 10, ["Automation", "Sandbox"], now - timedelta(days=1), "exe", "high", "Dangerous time sink."),
        Game("8", "Browser Puzzle Pack", "backlog", None, ["Puzzle"], None, "html", "medium", "HTML launcher."),
        Game("9", "Old Game Dump", "backlog", None, ["Unknown"], None, "exe", "low", "Needs review."),
        Game("10", "Co-op Party Night", "backlog", None, ["Co-op"], None, "exe", "medium", ""),
    ]
