from __future__ import annotations
from typing import Any, Dict, List

from app.models import Game, Collection

def apply_smart_filter(games: List[Game], f: Dict[str, Any]) -> List[Game]:
    """
    Supported keys:
      - status_in: [..]
      - rating_min: int
      - tag_any: [..]
      - shortcut_type_in: [..]    (lnk/url/html)
      - confidence_in: [..]       (high/medium/low)
      - unplayed: bool            (launch_count == 0)
      - launch_count_max: int
    """
    out = []
    for g in games:
        if "status_in" in f and g.status not in set(f["status_in"]):
            continue
        if "rating_min" in f:
            rmin = int(f["rating_min"])
            if g.rating is None or g.rating < rmin:
                continue
        if "tag_any" in f:
            want = {t.lower() for t in f["tag_any"]}
            have = {t.lower() for t in g.tags}
            if want and have.isdisjoint(want):
                continue
        if "shortcut_type_in" in f:
            if (g.shortcut_type or "") not in set(f["shortcut_type_in"]):
                continue
        if "confidence_in" in f:
            if g.confidence not in set(f["confidence_in"]):
                continue
        if f.get("unplayed") is True and g.launch_count != 0:
            continue
        if "launch_count_max" in f:
            try:
                lcmax = int(f["launch_count_max"])
                if g.launch_count > lcmax:
                    continue
            except Exception:
                pass

        out.append(g)
    return out


def apply_collection(games: List[Game], c: Collection) -> List[Game]:
    if c.type == "manual":
        game_ids = getattr(c, "game_ids", []) or getattr(c, "manual_game_ids", []) or []
        wanted = set(game_ids)
        return [g for g in games if g.game_id in wanted]
    return apply_smart_filter(games, c.filter)
