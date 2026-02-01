from __future__ import annotations
from dataclasses import dataclass
import re
from enum import Enum
from typing import List, Optional, Tuple

from app.logging_utils import get_logger, kv, RateLimiter

_log = get_logger("version_parser")
_rate = RateLimiter()


class VersionKind(Enum):
    NUMERIC = "numeric"
    BUILD = "build"
    SEASON = "season"
    UNKNOWN = "unknown"


class CompareResult(Enum):
    NEWER = 1
    OLDER = -1
    SAME = 0
    UNKNOWN = None


@dataclass
class VersionInfo:
    raw: str
    kind: VersionKind
    numeric: Optional[Tuple[int, ...]] = None
    suffix_letter: Optional[str] = None   # a, b, etc.
    label: str = ""                       # demo/patreon/etc.

    @property
    def numeric_str(self) -> Optional[str]:
        return ".".join(str(x) for x in self.numeric) if self.numeric else None


_RE_NUMERIC = re.compile(r"(\d+(?:\.\d+)+|\d+)([a-zA-Z]?)")
_RE_BUILD = re.compile(r"\bbuild\s+(\d+(?:\.\d+)*)", re.IGNORECASE)
_RE_SEASON = re.compile(r"\bseason\s+(\d+)", re.IGNORECASE)


def _coerce_numeric(text: str) -> Optional[Tuple[int, ...]]:
    parts = []
    for seg in text.split("."):
        try:
            parts.append(int(seg))
        except Exception:
            return None
    return tuple(parts) if parts else None


def parse_version(raw: str) -> VersionInfo:
    if not raw:
        return VersionInfo(raw="", kind=VersionKind.UNKNOWN)

    txt = raw.strip()

    # Build
    m = _RE_BUILD.search(txt)
    if m:
        num = _coerce_numeric(m.group(1))
        return VersionInfo(raw=raw, kind=VersionKind.BUILD, numeric=num, label="build")

    # Season
    m = _RE_SEASON.search(txt)
    if m:
        num = _coerce_numeric(m.group(1))
        return VersionInfo(raw=raw, kind=VersionKind.SEASON, numeric=num)

    # Numeric with optional suffix letter
    m = _RE_NUMERIC.search(txt)
    if m:
        num = _coerce_numeric(m.group(1))
        suffix_letter = m.group(2).lower() or None
        # labels
        label = ""
        lowered = txt.lower()
        for kw in ("patreon", "redux", "demo", "beta", "alpha", "hotfix"):
            if kw in lowered:
                label = kw
                break
        return VersionInfo(raw=raw, kind=VersionKind.NUMERIC, numeric=num, suffix_letter=suffix_letter, label=label)

    # Unknown textual label only
    if _rate.allow("version_unknown", 1000):
        _log.debug("version_unknown %s", kv(raw=txt[:80]))
    return VersionInfo(raw=raw, kind=VersionKind.UNKNOWN, label=txt)


def _cmp_suffix(a: Optional[str], b: Optional[str]) -> Optional[int]:
    # None beats letter (release > prerelease)
    if a == b:
        return 0
    if a is None and b is not None:
        return 1
    if a is not None and b is None:
        return -1
    # both letters
    return (1 if a > b else -1) if a != b else 0


def compare_versions(a: Optional[VersionInfo], b: Optional[VersionInfo]) -> CompareResult:
    """
    Returns NEWER if a>b (installed newer than source),
            OLDER if a<b (installed older),
            SAME,
            UNKNOWN when ordering can't be decided.
    """
    if a is None or b is None:
        return CompareResult.UNKNOWN

    # same kind numeric comparisons
    if a.kind == b.kind:
        if a.kind in (VersionKind.NUMERIC, VersionKind.BUILD, VersionKind.SEASON):
            if not a.numeric or not b.numeric:
                return CompareResult.UNKNOWN
            if a.numeric == b.numeric:
                suf_cmp = _cmp_suffix(a.suffix_letter, b.suffix_letter)
                if suf_cmp is None:
                    return CompareResult.UNKNOWN
                if suf_cmp == 0:
                    return CompareResult.SAME
                return CompareResult.NEWER if suf_cmp > 0 else CompareResult.OLDER
            return CompareResult.NEWER if a.numeric > b.numeric else CompareResult.OLDER
        return CompareResult.UNKNOWN

    # Mixed kinds: numeric/build/season vs unknown
    priority = {VersionKind.NUMERIC: 3, VersionKind.BUILD: 2, VersionKind.SEASON: 2, VersionKind.UNKNOWN: 1}
    ka = priority.get(a.kind, 0)
    kb = priority.get(b.kind, 0)
    if ka != kb and (a.numeric and b.numeric):
        if a.numeric == b.numeric:
            suf_cmp = _cmp_suffix(a.suffix_letter, b.suffix_letter)
            if suf_cmp is None:
                return CompareResult.UNKNOWN
            if suf_cmp == 0:
                return CompareResult.SAME
            return CompareResult.NEWER if suf_cmp > 0 else CompareResult.OLDER
        return CompareResult.NEWER if a.numeric > b.numeric else CompareResult.OLDER

    return CompareResult.UNKNOWN
