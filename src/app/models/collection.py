from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

CollectionType = Literal["manual", "smart"]

@dataclass
class Collection:
    collection_id: str
    name: str
    type: CollectionType = "manual"

    # manual collections
    game_ids: List[str] = field(default_factory=list)

    # smart collections (filters)
    # Example:
    # {"status_in":["backlog"], "rating_min":8, "tag_any":["Co-op"], "shortcut_type_in":["html"]}
    filter: Dict[str, Any] = field(default_factory=dict)
