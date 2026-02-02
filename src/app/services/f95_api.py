from __future__ import annotations
"""
F95zone API abstraction layer.

Provides high-level methods for interacting with F95zone:
- Thread metadata extraction (title, developer, tags, category)
- Download link parsing
- Version changelog extraction
- URL normalization
"""

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse, urljoin
from hashlib import md5

from lxml import html

from app.logging_utils import get_logger, kv, RateLimiter, timed

_log = get_logger("f95_api")
_rate = RateLimiter()

# Common F95zone URL patterns
F95_DOMAINS = {"f95zone.to", "f95zone.com", "www.f95zone.to", "www.f95zone.com"}
THREAD_URL_RE = re.compile(r"/threads/(?:([^/]+?)\.)?(\d+)/?")
POST_URL_RE = re.compile(r"/goto/post\?id=(\d+)")

# Thread title parsing
TITLE_RE = re.compile(
    r"^\s*\[([^\]]+)\]\s*(.+?)\s*\[([^\]]+)\]\s*(?:\[([^\]]+)\])?\s*$"
)
# Fallback: [Tag] Title [Developer]
TITLE_FALLBACK_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(.+?)\s*\[([^\]]+)\]\s*$")

# Download link patterns - mapped to host types with priorities
# Lower priority = try first (better host)
DOWNLOAD_HOSTS = {
    # Priority 1: Buzzheavier (best)
    "buzzheavier.com": "buzzheavier",
    "bhvr.cc": "buzzheavier",
    # Priority 2: Gofile (reliable)
    "gofile.io": "gofile",
    # Priority 3: Pixeldrain (good but has limits)
    "pixeldrain.com": "pixeldrain",
    # Priority 4: MEGA (good but has quota)
    "mega.nz": "mega",
    "mega.co.nz": "mega",
    # Priority 5: Google Drive (reliable)
    "drive.google.com": "gdrive",
    "docs.google.com": "gdrive",
    # Priority 6: MediaFire (generally reliable)
    "mediafire.com": "mediafire",
    # Priority 7: Workupload (decent)
    "workupload.com": "workupload",
    # Priority 8+: Less reliable hosts
    "anonfiles.com": "anonfiles",
    "anonfiles.me": "anonfiles",
    "filechan.org": "anonfiles",
    "uploadhaven.com": "uploadhaven",
    "mixdrop.co": "mixdrop",
    "katfile.com": "katfile",
    "bowfile.com": "bowfile",
    "letsupload.cc": "anonfiles",
    "zippyshare.day": "direct",  # Zippyshare is dead, use direct
}

# Host priority ranking (lower = better)
HOST_PRIORITY = {
    "buzzheavier": 1,
    "gofile": 2,
    "pixeldrain": 3,
    "mega": 4,
    "gdrive": 5,
    "mediafire": 6,
    "workupload": 7,
    "anonfiles": 8,
    "uploadhaven": 9,
    "mixdrop": 10,
    "katfile": 11,
    "bowfile": 12,
    "direct": 99,
}

# Version/changelog patterns
CHANGELOG_HEADER_RE = re.compile(r"(?i)(?:change\s*log|what'?s?\s*new|updates?|patch\s*notes?)")
VERSION_HEADER_RE = re.compile(r"(?i)^v(?:ersion)?\s*[:\-]?\s*(.+)")


@dataclass
class ThreadInfo:
    """Extracted information from an F95zone thread."""
    thread_id: int
    url: str
    title: str = ""
    developer: str = ""
    version: str = ""
    category: str = ""  # Completed, Ongoing, Abandoned, etc.
    tags: List[str] = field(default_factory=list)
    overview: str = ""
    download_links: List["DownloadLink"] = field(default_factory=list)
    changelog: str = ""
    last_updated: str = ""
    thread_date: str = ""
    likes: int = 0
    replies: int = 0


@dataclass
class DownloadLink:
    """A download link extracted from a thread."""
    url: str
    host: str
    host_type: str  # mega, gdrive, pixeldrain, etc.
    label: str = ""  # User-provided label (e.g., "Windows", "Mac", "Android")
    version: str = ""
    file_size: str = ""
    is_direct: bool = False
    priority: int = 50  # Lower = better (try first)
    is_available: bool = True  # Set to False if file not found
    error: str = ""  # Error message if unavailable

    def __post_init__(self):
        """Set priority based on host type."""
        self.priority = HOST_PRIORITY.get(self.host_type, 50)


# In-memory cache for thread info
_thread_cache: Dict[int, Tuple[ThreadInfo, float]] = {}
_CACHE_TTL = 60 * 60 * 6  # 6 hours


def normalize_f95_url(url: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Normalize any F95zone URL to canonical form.
    Returns (canonical_url, thread_id) or (None, None) if not an F95 URL.
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check if it's an F95 domain
        if not any(d in domain for d in F95_DOMAINS):
            return None, None

        path = parsed.path

        # Try to extract thread ID from various URL formats
        thread_match = THREAD_URL_RE.search(path)
        if thread_match:
            thread_id = int(thread_match.group(2))
            return f"https://f95zone.to/threads/{thread_id}/", thread_id

        post_match = POST_URL_RE.search(url)
        if post_match:
            # Post redirect - we'd need to fetch to get thread ID
            return url, None

        return None, None
    except Exception as e:
        _log.warning("url_normalize_error %s", kv(url=url, err=str(e)))
        return None, None


def is_f95_url(url: str) -> bool:
    """Check if URL is an F95zone URL."""
    try:
        parsed = urlparse(url)
        return any(d in parsed.netloc.lower() for d in F95_DOMAINS)
    except Exception:
        return False


def extract_thread_id(url: str) -> Optional[int]:
    """Extract thread ID from F95zone URL."""
    _, thread_id = normalize_f95_url(url)
    return thread_id


def parse_thread_title(raw_title: str) -> Tuple[str, str, str, List[str]]:
    """
    Parse F95zone thread title format.
    Format: [Category] Game Title [Developer] [Version]

    Returns: (game_title, developer, version, [category_tags])
    """
    raw_title = raw_title.strip()

    # Try full pattern with version
    match = TITLE_RE.match(raw_title)
    if match:
        category = match.group(1).strip()
        title = match.group(2).strip()
        developer = match.group(3).strip()
        version = (match.group(4) or "").strip()
        return title, developer, version, [category]

    # Try pattern without version
    match = TITLE_FALLBACK_RE.match(raw_title)
    if match:
        category = match.group(1).strip()
        title = match.group(2).strip()
        developer = match.group(3).strip()
        return title, developer, "", [category]

    # No brackets - return as-is
    return raw_title, "", "", []


def extract_download_links(html_text: str) -> List[DownloadLink]:
    """
    Extract download links from F95zone thread HTML.
    Looks for links to known file hosts in the first post.
    Returns links sorted by priority (best hosts first).
    """
    links = []
    seen_urls = set()

    # Known ad/tracker domains to skip
    AD_DOMAINS = {
        "bit.ly", "tinyurl.com", "adf.ly", "ouo.io", "bc.vc",
        "linkvertise.com", "shrinkme.io", "exe.io", "sub2unlock.com",
        "adshrink.it", "linkshrink.net", "adyou.me", "za.gl",
    }

    # Patterns indicating ad/fake links
    AD_PATTERNS = [
        r"javascript:",
        r"void\(0\)",
        r"onclick.*popup",
        r"onclick.*window\.open",
        r"#\s*$",
    ]

    try:
        doc = html.fromstring(html_text)

        # Find all links in first post
        first_post_xpaths = [
            "//article[contains(@class,'message')][1]//a[@href]",
            "//div[contains(@class,'message-content')][1]//a[@href]",
            "//div[contains(@class,'bbWrapper')][1]//a[@href]",
        ]

        for xpath in first_post_xpaths:
            try:
                anchors = doc.xpath(xpath)
                for a in anchors:
                    href = a.get("href", "")
                    if not href or href in seen_urls:
                        continue

                    # Skip obviously bad URLs
                    if any(re.search(p, href, re.IGNORECASE) for p in AD_PATTERNS):
                        continue

                    # Check if it's a known download host
                    try:
                        parsed = urlparse(href)
                        domain = parsed.netloc.lower().replace("www.", "")

                        # Skip ad domains
                        if any(ad in domain for ad in AD_DOMAINS):
                            continue

                        host_type = None
                        for host_domain, htype in DOWNLOAD_HOSTS.items():
                            if host_domain in domain:
                                host_type = htype
                                break

                        if host_type:
                            # Get link text as label
                            label = a.text_content().strip() if a.text_content() else ""
                            label = label[:100]  # Limit length

                            # Skip if label indicates an ad
                            if any(ad in label.lower() for ad in ["sponsor", "advertisement", "ads"]):
                                continue

                            # Parse file size from label if present
                            file_size = ""
                            size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:MB|GB|KB))", label, re.IGNORECASE)
                            if size_match:
                                file_size = size_match.group(1)

                            # Check for version in label
                            version = ""
                            version_match = re.search(r"v?(\d+\.\d+(?:\.\d+)?)", label)
                            if version_match:
                                version = version_match.group(1)

                            links.append(DownloadLink(
                                url=href,
                                host=domain,
                                host_type=host_type,
                                label=label,
                                file_size=file_size,
                                version=version,
                            ))
                            seen_urls.add(href)
                    except Exception:
                        continue
            except Exception:
                continue

        # Sort links by priority (lower = better)
        links.sort(key=lambda x: (x.priority, x.host_type))

        if links and _rate.allow("download_links_found", 1000):
            _log.info("download_links_found %s", kv(
                count=len(links),
                hosts=[l.host_type for l in links[:5]]  # Log first 5 hosts
            ))

    except Exception as e:
        _log.warning("extract_download_links_error %s", kv(err=str(e)))

    return links


def extract_thread_info(html_text: str, url: str) -> ThreadInfo:
    """
    Extract comprehensive thread information from HTML.
    """
    thread_id = extract_thread_id(url) or 0
    info = ThreadInfo(thread_id=thread_id, url=url)

    try:
        doc = html.fromstring(html_text)

        # Extract title from page
        title_xpaths = [
            "//h1[contains(@class,'p-title-value')]/text()",
            "//div[contains(@class,'p-title')]//text()",
            "//title/text()",
        ]

        raw_title = ""
        for xpath in title_xpaths:
            try:
                nodes = doc.xpath(xpath)
                for n in nodes:
                    if isinstance(n, str) and n.strip():
                        raw_title = n.strip()
                        break
                if raw_title:
                    break
            except Exception:
                continue

        if raw_title:
            # Remove " | F95zone" suffix if present
            raw_title = re.sub(r"\s*\|\s*F95zone.*$", "", raw_title, flags=re.IGNORECASE)
            info.title, info.developer, info.version, tags = parse_thread_title(raw_title)
            info.tags.extend(tags)

        # Extract category from breadcrumbs or tags
        category_xpaths = [
            "//ul[contains(@class,'p-breadcrumbs')]//span[@itemprop='name']/text()",
            "//nav[contains(@class,'breadcrumb')]//a/text()",
        ]

        for xpath in category_xpaths:
            try:
                nodes = doc.xpath(xpath)
                for n in nodes:
                    if isinstance(n, str):
                        cat = n.strip()
                        if cat.lower() in ("completed", "ongoing", "abandoned", "on hold"):
                            info.category = cat
                            break
            except Exception:
                continue

        # Extract tags from tag list
        tag_xpaths = [
            "//a[contains(@class,'tagItem')]/text()",
            "//span[contains(@class,'js-tagList')]//a/text()",
        ]

        for xpath in tag_xpaths:
            try:
                nodes = doc.xpath(xpath)
                for n in nodes:
                    if isinstance(n, str) and n.strip():
                        tag = n.strip().lower()
                        if tag and tag not in info.tags:
                            info.tags.append(tag)
            except Exception:
                continue

        # Extract overview/description
        overview_xpaths = [
            "//article[contains(@class,'message')][1]//div[contains(@class,'bbWrapper')]",
        ]

        for xpath in overview_xpaths:
            try:
                nodes = doc.xpath(xpath)
                if nodes:
                    text_parts = nodes[0].text_content().split('\n')[:10]
                    info.overview = '\n'.join(line.strip() for line in text_parts if line.strip())[:500]
                    break
            except Exception:
                continue

        # Extract download links
        info.download_links = extract_download_links(html_text)

        # Extract changelog (look for Changelog/What's New sections)
        try:
            spoiler_xpaths = [
                "//div[contains(@class,'bbCodeSpoiler')]//div[contains(@class,'bbCodeBlock-content')]",
            ]
            for xpath in spoiler_xpaths:
                spoilers = doc.xpath(xpath)
                for spoiler in spoilers:
                    text = spoiler.text_content()
                    if CHANGELOG_HEADER_RE.search(text[:100]):
                        info.changelog = text.strip()[:2000]
                        break
                if info.changelog:
                    break
        except Exception:
            pass

        # Extract thread stats
        try:
            # Likes
            likes_nodes = doc.xpath("//a[contains(@class,'reactionsBar-link')]//bdi/text()")
            if likes_nodes:
                likes_str = likes_nodes[0].replace(",", "")
                if likes_str.isdigit():
                    info.likes = int(likes_str)

            # Replies
            replies_nodes = doc.xpath("//li[contains(text(),'Replies')]/following-sibling::dd/text()")
            if not replies_nodes:
                replies_nodes = doc.xpath("//dl[contains(.,'Replies')]//dd/text()")
            if replies_nodes:
                replies_str = str(replies_nodes[0]).strip().replace(",", "")
                if replies_str.isdigit():
                    info.replies = int(replies_str)
        except Exception:
            pass

        _log.info("thread_info_extracted %s", kv(
            thread_id=thread_id,
            title=info.title[:50] if info.title else "",
            developer=info.developer,
            version=info.version,
            category=info.category,
            tags=len(info.tags),
            links=len(info.download_links),
        ))

    except Exception as e:
        _log.warning("extract_thread_info_error %s", kv(url=url, err=str(e)))

    return info


def get_cached_thread_info(thread_id: int) -> Optional[ThreadInfo]:
    """Get thread info from cache if still valid."""
    if thread_id in _thread_cache:
        info, ts = _thread_cache[thread_id]
        if time.time() - ts < _CACHE_TTL:
            return info
        del _thread_cache[thread_id]
    return None


def cache_thread_info(info: ThreadInfo) -> None:
    """Store thread info in cache."""
    if info.thread_id:
        _thread_cache[info.thread_id] = (info, time.time())


def clear_thread_cache() -> None:
    """Clear the thread info cache."""
    _thread_cache.clear()
    _log.info("thread_cache_cleared")


def derive_title_from_url(url: str) -> str:
    """
    Extract a probable game title from an F95zone URL slug.
    Used when we can't fetch the page.
    """
    match = THREAD_URL_RE.search(url)
    if match and match.group(1):
        slug = match.group(1)
        # Convert slug to title (replace hyphens/underscores with spaces)
        title = re.sub(r"[-_]+", " ", slug)
        # Remove version numbers
        title = re.sub(r"\b(v|ver|version|build|season)\s*[\d.]+.*$", "", title, flags=re.IGNORECASE)
        # Clean up
        title = re.sub(r"\s+", " ", title).strip()
        return title.title()
    return ""


def group_download_links_by_version(links: List[DownloadLink]) -> Dict[str, List[DownloadLink]]:
    """
    Group download links by version if version info is available.
    Returns dict with version as key and links as value.
    """
    groups: Dict[str, List[DownloadLink]] = {"latest": []}

    for link in links:
        if link.version:
            if link.version not in groups:
                groups[link.version] = []
            groups[link.version].append(link)
        else:
            groups["latest"].append(link)

    # If no versioned links, everything is "latest"
    if len(groups) == 1 and "latest" in groups:
        return groups

    # Remove empty "latest" if we have versioned links
    if not groups["latest"] and len(groups) > 1:
        del groups["latest"]

    return groups


def group_download_links_by_host(links: List[DownloadLink]) -> Dict[str, List[DownloadLink]]:
    """
    Group download links by host type.
    Returns dict with host_type as key and links as value.
    """
    groups: Dict[str, List[DownloadLink]] = {}

    for link in links:
        if link.host_type not in groups:
            groups[link.host_type] = []
        groups[link.host_type].append(link)

    return groups


def get_best_download_link(links: List[DownloadLink], skip_hosts: Optional[List[str]] = None) -> Optional[DownloadLink]:
    """
    Get the best available download link based on priority.

    Args:
        links: List of download links
        skip_hosts: List of host types to skip (e.g., hosts at their daily limit)

    Returns:
        Best available DownloadLink or None
    """
    skip_hosts = skip_hosts or []

    available_links = [
        link for link in links
        if link.is_available and link.host_type not in skip_hosts
    ]

    if not available_links:
        return None

    # Sort by priority and return best
    available_links.sort(key=lambda x: (x.priority, x.host_type))
    return available_links[0]


def get_fallback_links(links: List[DownloadLink], failed_host: str) -> List[DownloadLink]:
    """
    Get alternative download links after a host fails.

    Args:
        links: All download links
        failed_host: Host type that failed

    Returns:
        List of alternative links sorted by priority
    """
    alternatives = [
        link for link in links
        if link.host_type != failed_host and link.is_available
    ]
    alternatives.sort(key=lambda x: (x.priority, x.host_type))
    return alternatives


def mark_link_unavailable(links: List[DownloadLink], url: str, error: str = "") -> None:
    """
    Mark a download link as unavailable (e.g., 404).

    Args:
        links: List of download links to update
        url: URL of the unavailable link
        error: Error message
    """
    for link in links:
        if link.url == url:
            link.is_available = False
            link.error = error
            break


def get_host_display_info(host_type: str) -> Dict[str, any]:
    """
    Get display information for a host type.

    Returns dict with:
        - name: Display name
        - priority: Priority ranking
        - has_limit: Whether host has daily limits
        - notes: Any important notes
    """
    host_info = {
        "buzzheavier": {
            "name": "Buzzheavier",
            "priority": 1,
            "has_limit": False,
            "notes": "Fast and reliable, best choice",
        },
        "gofile": {
            "name": "Gofile",
            "priority": 2,
            "has_limit": False,
            "notes": "Reliable with minimal limits",
        },
        "pixeldrain": {
            "name": "Pixeldrain",
            "priority": 3,
            "has_limit": True,
            "notes": "~6GB daily limit for free users",
        },
        "mega": {
            "name": "MEGA",
            "priority": 4,
            "has_limit": True,
            "notes": "~5GB transfer quota every 6 hours",
        },
        "gdrive": {
            "name": "Google Drive",
            "priority": 5,
            "has_limit": False,
            "notes": "May require virus scan confirmation",
        },
        "mediafire": {
            "name": "MediaFire",
            "priority": 6,
            "has_limit": False,
            "notes": "Generally reliable",
        },
        "workupload": {
            "name": "Workupload",
            "priority": 7,
            "has_limit": False,
            "notes": "May have wait times",
        },
        "anonfiles": {
            "name": "Anonfiles",
            "priority": 8,
            "has_limit": False,
            "notes": "Service unreliable, may be down",
        },
    }
    return host_info.get(host_type, {
        "name": host_type.title(),
        "priority": HOST_PRIORITY.get(host_type, 50),
        "has_limit": False,
        "notes": "",
    })


def filter_links_by_platform(links: List[DownloadLink], platform: str) -> List[DownloadLink]:
    """
    Filter download links by platform (Windows, Mac, Android, Linux).

    Args:
        links: List of download links
        platform: Platform to filter for (case-insensitive)

    Returns:
        Links matching the platform, or all links if no matches
    """
    platform_lower = platform.lower()
    platform_patterns = {
        "windows": ["windows", "win", "pc"],
        "mac": ["mac", "macos", "osx", "apple"],
        "android": ["android", "apk"],
        "linux": ["linux", "unix"],
    }

    patterns = platform_patterns.get(platform_lower, [platform_lower])

    filtered = [
        link for link in links
        if any(p in link.label.lower() for p in patterns)
    ]

    # If no matches, return all links
    return filtered if filtered else links
