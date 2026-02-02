from __future__ import annotations
import urllib.request
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple
import time

from lxml import html

from hashlib import md5
from app.models import Game
from app.services.version_parser import parse_version, compare_versions, CompareResult, VersionInfo
from app.services.f95_parser import extract_f95_version
from app.services.http_utils import USER_AGENT, create_request, DEFAULT_TIMEOUT
from app.logging_utils import get_logger
from app.logging_utils import kv, RateLimiter, timed

_log = get_logger("update_checker")
_rate = RateLimiter()

# Simple in-memory cache for fetched pages this session
_html_cache: Dict[str, str] = {}
_html_cache_ts: Dict[str, float] = {}
# cache parsed versions keyed by (url, content_hash)
_parsed_cache: Dict[Tuple[str, str], Tuple[str, str, str]] = {}
_CACHE_TTL = 60 * 60 * 6  # 6 hours


def _fetch(url: str) -> str:
    now = time.time()
    if url in _html_cache and now - _html_cache_ts.get(url, 0) < _CACHE_TTL:
        if _rate.allow("fetch_cache_hit", 1000):
            _log.debug("fetch_cache_hit %s", kv(url=url))
        return _html_cache[url]

    last_err = None
    for attempt in range(3):
        try:
            # Use shared http_utils for request creation
            req = create_request(url)
            with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                _html_cache[url] = text
                _html_cache_ts[url] = time.time()
                _log.info("fetch_ok %s", kv(url=url, status=resp.status, len=len(text), attempt=attempt+1))
                return text
        except Exception as e:
            last_err = e
            _log.warning("fetch_retry %s", kv(url=url, attempt=attempt+1, err=e))
            time.sleep(1.5)
    raise last_err or RuntimeError("fetch failed")


def _extract_text_first(doc, xpath_expr: str) -> Optional[str]:
    try:
        nodes = doc.xpath(xpath_expr)
    except Exception:
        return None
    for n in nodes:
        txt = (n if isinstance(n, str) else getattr(n, "text", None)) or ""
        txt = txt.strip()
        if txt:
            return txt
    return None


def parse_source_version(html_text: str) -> Tuple[str, Optional[str], str]:
    """Legacy generic parser retained for non-f95 pages. Returns (raw, num_str, suffix)."""
    doc = html.fromstring(html_text)

    candidates = [
        "//header//text()[contains(translate(., 'VERSION', 'version'), 'version')]",
        "//text()[contains(translate(., 'VERSION', 'version'), 'version')][1]",
    ]
    raw = None
    for xp in candidates:
        raw = _extract_text_first(doc, xp)
        if raw:
            break

    raw = raw or ""
    vi = parse_version(raw)
    return raw, vi.numeric_str, vi.suffix_letter or ""


def fetch_source_version(url: str) -> Tuple[str, Optional[str], str]:
    html_text = _fetch(url)
    h = md5(html_text.encode("utf-8", errors="ignore")).hexdigest()
    cache_key = (url, h)
    if cache_key in _parsed_cache:
        if _rate.allow("parse_cache_hit", 1000):
            _log.debug("parse_cache_hit %s", kv(url=url))
        return _parsed_cache[cache_key]

    # f95 special handling
    if "f95zone" in url:
        raw, method = extract_f95_version(html_text)
        if raw:
            vi = parse_version(raw)
            result = (raw, vi.numeric_str, vi.suffix_letter or "")
            _parsed_cache[cache_key] = result
            return result
        _log.info("f95 parser returned none; method=%s", method)

    result = parse_source_version(html_text)
    _parsed_cache[cache_key] = result
    if _rate.allow("parse_done", 800):
        _log.info("parse_done %s", kv(url=url, raw=result[0][:50], num=result[1], suf=result[2]))
    return result


def check_updates_background(
    games: List[Game],
    progress: Optional[Callable[[str, int, int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> List[Dict[str, object]]:
    """
    Fetch + parse source versions for games with source_url.
    Mutates games in place.
    Returns list of result dicts for UI consumption.
    """
    results: List[Dict[str, object]] = []
    total = len([g for g in games if g.source_url])
    done = 0
    now = datetime.now()

    for g in games:
        if cancel and cancel():
            _log.info("updates_cancel %s", kv(done=done, total=total))
            break
        if not g.source_url:
            results.append({"game_id": g.game_id, "status": "no_source"})
            continue
        try:
            with timed(_log, "update_fetch", event="update_fetch", game_id=g.game_id, url=g.source_url, title=g.title):
                raw, num_str, suffix = fetch_source_version(g.source_url)
                g.source_version_raw = raw
                g.source_version_num = num_str
                g.source_version_suffix = suffix
                g.source_checked_at = now

                inst_vi = parse_version(g.installed_version_raw) if g.installed_version_raw else None
                src_vi = parse_version(raw) if raw else None
                cmp = compare_versions(inst_vi, src_vi)

                results.append({
                    "game_id": g.game_id,
                    "status": "ok",
                    "source_version_raw": raw,
                    "source_version_num": num_str,
                    "source_version_suffix": suffix,
                    "installed_version_num": inst_vi.numeric_str if inst_vi else None,
                    "compare": cmp,
                })
        except Exception as e:
            _log.warning("update_fetch_error %s", kv(game_id=g.game_id, title=g.title, url=g.source_url, err=e))
            results.append({"game_id": g.game_id, "status": "error", "error": str(e)})

        done += 1
        if progress:
            progress(f"Checking updates {done}/{total}", done, total)
        if _rate.allow("update_progress", 500):
            _log.debug("update_progress %s", kv(done=done, total=total))

    return results
