"""Custom XPath paths configuration for scraping additional game data.

Allows users and developers to define XPath expressions to extract
specific data from F95zone thread pages (or other sources). These
paths can be stored per-game or as global defaults.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class CustomXPaths:
    """User/developer-configurable XPath expressions for data extraction.

    Each field is an XPath expression that targets a specific piece of
    data on the source page. Empty strings mean 'use default' or 'skip'.
    """
    # Overview / description from the thread
    description: str = ""
    # Banner / header image
    banner_image: str = ""
    # Cheat codes or walkthrough content
    cheat_codes: str = ""
    # Extra downloads (patches, mods, walkthroughs, save files)
    extras: List[str] = field(default_factory=list)
    # Genre / category tags beyond the default tag extraction
    genre_tags: str = ""
    # Developer info (if not in standard title format)
    developer_info: str = ""
    # Changelog / update notes
    changelog: str = ""
    # Rating or score from the page
    page_rating: str = ""
    # Any additional labeled paths: {"label": "xpath_expression"}
    custom: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "banner_image": self.banner_image,
            "cheat_codes": self.cheat_codes,
            "extras": self.extras,
            "genre_tags": self.genre_tags,
            "developer_info": self.developer_info,
            "changelog": self.changelog,
            "page_rating": self.page_rating,
            "custom": self.custom,
        }

    @classmethod
    def from_dict(cls, d: dict) -> CustomXPaths:
        if not d:
            return cls()
        return cls(
            description=d.get("description", ""),
            banner_image=d.get("banner_image", ""),
            cheat_codes=d.get("cheat_codes", ""),
            extras=d.get("extras", []),
            genre_tags=d.get("genre_tags", ""),
            developer_info=d.get("developer_info", ""),
            changelog=d.get("changelog", ""),
            page_rating=d.get("page_rating", ""),
            custom=d.get("custom", {}),
        )


# Default XPath expressions for F95zone threads
F95_DEFAULT_XPATHS = CustomXPaths(
    description=(
        "//article[contains(@class,'message')][1]"
        "//div[contains(@class,'bbWrapper')]"
    ),
    banner_image=(
        "//article[contains(@class,'message')][1]"
        "//div[contains(@class,'bbWrapper')]//img[1]/@src"
    ),
    cheat_codes=(
        "//div[contains(@class,'bbCodeSpoiler')]"
        "[.//span[contains(@class,'bbCodeSpoiler-button-title')]"
        "[contains(translate(text(),'CHEAT','cheat'),'cheat')]]"
        "//div[contains(@class,'bbCodeBlock-content')]"
    ),
    extras=[
        # Walkthrough spoiler
        (
            "//div[contains(@class,'bbCodeSpoiler')]"
            "[.//span[contains(@class,'bbCodeSpoiler-button-title')]"
            "[contains(translate(text(),'WALKTHROUGH','walkthrough'),'walkthrough')]]"
            "//div[contains(@class,'bbCodeBlock-content')]//a[@href]"
        ),
        # Mod/patch spoiler
        (
            "//div[contains(@class,'bbCodeSpoiler')]"
            "[.//span[contains(@class,'bbCodeSpoiler-button-title')]"
            "[contains(translate(text(),'MOD','mod'),'mod')]]"
            "//div[contains(@class,'bbCodeBlock-content')]//a[@href]"
        ),
        # Save file spoiler
        (
            "//div[contains(@class,'bbCodeSpoiler')]"
            "[.//span[contains(@class,'bbCodeSpoiler-button-title')]"
            "[contains(translate(text(),'SAVE','save'),'save')]]"
            "//div[contains(@class,'bbCodeBlock-content')]//a[@href]"
        ),
    ],
    genre_tags=(
        "//a[contains(@class,'tagItem')]/text()"
    ),
    developer_info="",
    changelog=(
        "//div[contains(@class,'bbCodeSpoiler')]"
        "[.//span[contains(@class,'bbCodeSpoiler-button-title')]"
        "[contains(translate(text(),'CHANGELOG','changelog'),'changelog')]]"
        "//div[contains(@class,'bbCodeBlock-content')]"
    ),
    page_rating="",
)
