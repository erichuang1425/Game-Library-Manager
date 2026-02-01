from __future__ import annotations
import re
from hashlib import md5
from typing import Optional, Tuple
from lxml import html
from app.logging_utils import get_logger
from app.services.version_parser import parse_version

_log = get_logger("f95_parser")

XPATHS = [
    # thread header / title meta areas
    "//div[contains(@class,'block-container')][1]//div[contains(@class,'message-content')]//text()",
    "//article[contains(@class,'message')][1]//div[contains(@class,'bbWrapper')]//text()",
    "//h1//text()",
    "//div[contains(@class,'p-title')]//text()",
    "//div[contains(@class,'message-userContent')]//text()",
]

LINE_RE = re.compile(r"(?i)\b(ver(?:sion)?|v|build|season)\s*[:\-]?\s*(.+)")


def extract_f95_version(html_text: str) -> Tuple[Optional[str], str]:
    """
    Returns (version_raw, method_used)
    method_used in {"xpath_header","line_scan","regex_body","none"}
    """
    doc = html.fromstring(html_text)

    # pass 1: structured XPaths
    for xp in XPATHS:
        try:
            texts = doc.xpath(xp)
        except Exception:
            continue
        for t in texts:
            if not isinstance(t, str):
                continue
            line = t.strip()
            if not line:
                continue
            m = LINE_RE.search(line)
            if m:
                candidate = m.group(2).strip()
                return candidate, "xpath_header"
    # pass 2: scan first post lines
    try:
        body_texts = doc.xpath("//article[contains(@class,'message')][1]//text()")
    except Exception:
        body_texts = []
    for t in body_texts:
        if not isinstance(t, str):
            continue
        for line in t.splitlines():
            line = line.strip()
            if not line:
                continue
            m = LINE_RE.search(line)
            if m:
                return m.group(2).strip(), "line_scan"

    # pass 3: regex over whole page but limited
    flat = " ".join([x for x in body_texts if isinstance(x, str)])
    m = LINE_RE.search(flat)
    if m:
        return m.group(2).strip(), "regex_body"

    debug_snippet = " | ".join([x.strip() for x in body_texts if isinstance(x, str)][:5])[:120]
    _log.debug("f95 parse none. first_lines=%s", debug_snippet)
    return None, "none"
