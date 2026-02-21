"""Tests for f95_api.py - F95zone API abstraction layer."""
import pytest
from app.services.f95_api import (
    normalize_f95_url,
    is_f95_url,
    extract_thread_id,
    parse_thread_title,
    extract_download_links,
    extract_thread_info,
    derive_title_from_url,
    group_download_links_by_version,
    group_download_links_by_host,
    get_best_download_link,
    get_fallback_links,
    mark_link_unavailable,
    get_host_display_info,
    filter_links_by_platform,
    DownloadLink,
    ThreadInfo,
    get_cached_thread_info,
    cache_thread_info,
    clear_thread_cache,
)


# ---- URL normalization ----

class TestNormalizeF95Url:
    def test_standard_thread_url(self):
        url = "https://f95zone.to/threads/some-game.12345/"
        canonical, tid = normalize_f95_url(url)
        assert canonical == "https://f95zone.to/threads/12345/"
        assert tid == 12345

    def test_thread_url_without_slug(self):
        url = "https://f95zone.to/threads/12345/"
        canonical, tid = normalize_f95_url(url)
        assert canonical == "https://f95zone.to/threads/12345/"
        assert tid == 12345

    def test_thread_url_no_trailing_slash(self):
        url = "https://f95zone.to/threads/some-game.12345"
        canonical, tid = normalize_f95_url(url)
        assert canonical == "https://f95zone.to/threads/12345/"
        assert tid == 12345

    def test_www_prefix(self):
        url = "https://www.f95zone.to/threads/game.99999/"
        canonical, tid = normalize_f95_url(url)
        assert canonical == "https://f95zone.to/threads/99999/"
        assert tid == 99999

    def test_f95zone_com_domain(self):
        url = "https://f95zone.com/threads/game.55555/"
        canonical, tid = normalize_f95_url(url)
        assert canonical == "https://f95zone.to/threads/55555/"
        assert tid == 55555

    def test_non_f95_url(self):
        url = "https://example.com/threads/12345/"
        canonical, tid = normalize_f95_url(url)
        assert canonical is None
        assert tid is None

    def test_empty_string(self):
        canonical, tid = normalize_f95_url("")
        assert canonical is None
        assert tid is None

    def test_post_redirect_url(self):
        url = "https://f95zone.to/goto/post?id=67890"
        canonical, tid = normalize_f95_url(url)
        # Post redirects return the URL but no thread_id
        assert canonical == url
        assert tid is None

    def test_invalid_url(self):
        canonical, tid = normalize_f95_url("not-a-url")
        assert canonical is None
        assert tid is None


class TestIsF95Url:
    def test_valid_f95zone_to(self):
        assert is_f95_url("https://f95zone.to/threads/game.123/") is True

    def test_valid_f95zone_com(self):
        assert is_f95_url("https://f95zone.com/threads/game.123/") is True

    def test_valid_www(self):
        assert is_f95_url("https://www.f95zone.to/threads/game.123/") is True

    def test_non_f95(self):
        assert is_f95_url("https://google.com") is False

    def test_empty(self):
        assert is_f95_url("") is False


class TestExtractThreadId:
    def test_standard(self):
        assert extract_thread_id("https://f95zone.to/threads/game.12345/") == 12345

    def test_no_slug(self):
        assert extract_thread_id("https://f95zone.to/threads/12345/") == 12345

    def test_non_f95(self):
        assert extract_thread_id("https://google.com") is None


# ---- Thread title parsing ----

class TestParseThreadTitle:
    def test_full_format_with_version(self):
        title = "[Completed] Some Great Game [DevName] [v1.0]"
        game, dev, ver, tags = parse_thread_title(title)
        assert game == "Some Great Game"
        assert dev == "DevName"
        assert ver == "v1.0"
        assert tags == ["Completed"]

    def test_without_version(self):
        title = "[Ongoing] Another Game [AnotherDev]"
        game, dev, ver, tags = parse_thread_title(title)
        assert game == "Another Game"
        assert dev == "AnotherDev"
        assert ver == ""
        assert tags == ["Ongoing"]

    def test_no_brackets(self):
        title = "Just A Plain Title"
        game, dev, ver, tags = parse_thread_title(title)
        assert game == "Just A Plain Title"
        assert dev == ""
        assert ver == ""
        assert tags == []

    def test_with_whitespace(self):
        title = "  [Abandoned]  My Game  [Some Dev]  [v2.0]  "
        game, dev, ver, tags = parse_thread_title(title)
        assert game == "My Game"
        assert dev == "Some Dev"
        assert ver == "v2.0"
        assert tags == ["Abandoned"]

    def test_empty(self):
        game, dev, ver, tags = parse_thread_title("")
        assert game == ""
        assert dev == ""
        assert ver == ""
        assert tags == []


# ---- Download link extraction ----

def _make_thread_html(links_html: str) -> str:
    """Build minimal F95zone-like HTML with download links."""
    return f"""
    <html><body>
    <article class="message">
      <div class="message-content">
        <div class="bbWrapper">
          <p>Game overview text</p>
          {links_html}
        </div>
      </div>
    </article>
    </body></html>
    """


class TestExtractDownloadLinks:
    def test_mega_link(self):
        html = _make_thread_html('<a href="https://mega.nz/file/abc123">MEGA Download</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "mega"
        assert links[0].url == "https://mega.nz/file/abc123"

    def test_gdrive_link(self):
        html = _make_thread_html('<a href="https://drive.google.com/file/d/123/view">Google Drive</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "gdrive"

    def test_pixeldrain_link(self):
        html = _make_thread_html('<a href="https://pixeldrain.com/u/abc123">Pixeldrain</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "pixeldrain"

    def test_buzzheavier_link(self):
        html = _make_thread_html('<a href="https://buzzheavier.com/f/abc123">Buzzheavier</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "buzzheavier"

    def test_gofile_link(self):
        html = _make_thread_html('<a href="https://gofile.io/d/abc123">Gofile</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "gofile"

    def test_mediafire_link(self):
        html = _make_thread_html('<a href="https://mediafire.com/file/abc123">MediaFire</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "mediafire"

    def test_workupload_link(self):
        html = _make_thread_html('<a href="https://workupload.com/file/abc123">Workupload</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "workupload"

    def test_multiple_hosts(self):
        html = _make_thread_html("""
            <a href="https://mega.nz/file/abc">MEGA</a>
            <a href="https://pixeldrain.com/u/xyz">Pixeldrain</a>
            <a href="https://buzzheavier.com/f/123">Buzzheavier</a>
        """)
        links = extract_download_links(html)
        assert len(links) == 3
        # Should be sorted by priority: buzzheavier (1) < pixeldrain (3) < mega (4)
        assert links[0].host_type == "buzzheavier"
        assert links[1].host_type == "pixeldrain"
        assert links[2].host_type == "mega"

    def test_duplicate_urls_deduplicated(self):
        html = _make_thread_html("""
            <a href="https://mega.nz/file/abc">MEGA</a>
            <a href="https://mega.nz/file/abc">MEGA again</a>
        """)
        links = extract_download_links(html)
        assert len(links) == 1

    def test_ad_domains_filtered(self):
        html = _make_thread_html("""
            <a href="https://mega.nz/file/abc">MEGA</a>
            <a href="https://bit.ly/xyz">Short Link</a>
            <a href="https://linkvertise.com/xyz">Ad Link</a>
        """)
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "mega"

    def test_javascript_links_filtered(self):
        html = _make_thread_html('<a href="javascript:void(0)">Fake Link</a>')
        links = extract_download_links(html)
        assert len(links) == 0

    def test_sponsor_label_filtered(self):
        html = _make_thread_html('<a href="https://mega.nz/file/abc">Sponsor Link</a>')
        links = extract_download_links(html)
        assert len(links) == 0

    def test_non_download_links_ignored(self):
        html = _make_thread_html("""
            <a href="https://example.com/page">Random Link</a>
            <a href="https://forum.example.com/thread">Forum Link</a>
        """)
        links = extract_download_links(html)
        assert len(links) == 0

    def test_file_size_extraction(self):
        html = _make_thread_html('<a href="https://mega.nz/file/abc">Download (1.5 GB)</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].file_size == "1.5 GB"

    def test_version_extraction_from_label(self):
        html = _make_thread_html('<a href="https://mega.nz/file/abc">v0.5.2 Download</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].version == "0.5.2"

    def test_empty_html(self):
        links = extract_download_links("<html><body></body></html>")
        assert len(links) == 0

    def test_bhvr_cc_is_buzzheavier(self):
        html = _make_thread_html('<a href="https://bhvr.cc/f/abc123">BHVR</a>')
        links = extract_download_links(html)
        assert len(links) == 1
        assert links[0].host_type == "buzzheavier"


# ---- Thread info extraction ----

class TestExtractThreadInfo:
    def test_basic_extraction(self):
        html = """
        <html><head><title>[Ongoing] Cool Game [DevName] [v1.2] | F95zone</title></head>
        <body>
        <h1 class="p-title-value">[Ongoing] Cool Game [DevName] [v1.2]</h1>
        <article class="message">
          <div class="bbWrapper">
            <p>This is the game overview.</p>
            <a href="https://mega.nz/file/abc">MEGA Download</a>
          </div>
        </article>
        </body></html>
        """
        info = extract_thread_info(html, "https://f95zone.to/threads/cool-game.12345/")
        assert info.thread_id == 12345
        assert info.title == "Cool Game"
        assert info.developer == "DevName"
        assert info.version == "v1.2"
        assert "Ongoing" in info.tags
        assert len(info.download_links) == 1

    def test_extracts_overview(self):
        html = """
        <html><body>
        <h1 class="p-title-value">Test Game</h1>
        <article class="message">
          <div class="bbWrapper">
            <p>This is the game description and overview text.</p>
          </div>
        </article>
        </body></html>
        """
        info = extract_thread_info(html, "https://f95zone.to/threads/test.100/")
        assert "description" in info.overview.lower() or "overview" in info.overview.lower()

    def test_thread_id_from_url(self):
        html = "<html><body></body></html>"
        info = extract_thread_info(html, "https://f95zone.to/threads/game.99999/")
        assert info.thread_id == 99999

    def test_removes_f95zone_suffix_from_title(self):
        html = """
        <html><body>
        <h1 class="p-title-value">My Game | F95zone Forum</h1>
        </body></html>
        """
        info = extract_thread_info(html, "https://f95zone.to/threads/game.100/")
        assert "F95zone" not in info.title

    def test_extracts_tags(self):
        html = """
        <html><body>
        <h1 class="p-title-value">Test</h1>
        <a class="tagItem">tag1</a>
        <a class="tagItem">tag2</a>
        <a class="tagItem">tag3</a>
        </body></html>
        """
        info = extract_thread_info(html, "https://f95zone.to/threads/test.100/")
        assert "tag1" in info.tags
        assert "tag2" in info.tags
        assert "tag3" in info.tags

    def test_empty_html(self):
        info = extract_thread_info("<html><body></body></html>", "https://f95zone.to/threads/test.100/")
        assert info.thread_id == 100
        assert info.title == ""
        assert info.download_links == []


# ---- Derive title from URL ----

class TestDeriveTitleFromUrl:
    def test_standard_slug(self):
        title = derive_title_from_url("https://f95zone.to/threads/my-awesome-game.12345/")
        assert title == "My Awesome Game"

    def test_slug_with_version(self):
        title = derive_title_from_url("https://f95zone.to/threads/cool-game-v0-5.12345/")
        assert "Cool Game" in title
        # Version part should be removed
        assert "v0" not in title.lower() or "v0-5" not in title.lower()

    def test_slug_with_underscores(self):
        title = derive_title_from_url("https://f95zone.to/threads/some_game_title.12345/")
        assert title == "Some Game Title"

    def test_no_slug(self):
        title = derive_title_from_url("https://f95zone.to/threads/12345/")
        assert title == ""

    def test_non_f95_url(self):
        title = derive_title_from_url("https://example.com/")
        assert title == ""


# ---- Download link grouping ----

class TestGroupDownloadLinksByVersion:
    def test_mixed_versions(self):
        links = [
            DownloadLink(url="a", host="mega.nz", host_type="mega", version="1.0"),
            DownloadLink(url="b", host="mega.nz", host_type="mega", version="1.0"),
            DownloadLink(url="c", host="mega.nz", host_type="mega", version="2.0"),
            DownloadLink(url="d", host="mega.nz", host_type="mega"),
        ]
        groups = group_download_links_by_version(links)
        assert "1.0" in groups
        assert len(groups["1.0"]) == 2
        assert "2.0" in groups
        assert len(groups["2.0"]) == 1

    def test_no_versions(self):
        links = [
            DownloadLink(url="a", host="mega.nz", host_type="mega"),
            DownloadLink(url="b", host="mega.nz", host_type="mega"),
        ]
        groups = group_download_links_by_version(links)
        assert "latest" in groups
        assert len(groups["latest"]) == 2


class TestGroupDownloadLinksByHost:
    def test_multiple_hosts(self):
        links = [
            DownloadLink(url="a", host="mega.nz", host_type="mega"),
            DownloadLink(url="b", host="pixeldrain.com", host_type="pixeldrain"),
            DownloadLink(url="c", host="mega.nz", host_type="mega"),
        ]
        groups = group_download_links_by_host(links)
        assert "mega" in groups
        assert len(groups["mega"]) == 2
        assert "pixeldrain" in groups
        assert len(groups["pixeldrain"]) == 1


# ---- Best link selection ----

class TestGetBestDownloadLink:
    def test_returns_highest_priority(self):
        links = [
            DownloadLink(url="a", host="mega.nz", host_type="mega"),
            DownloadLink(url="b", host="buzzheavier.com", host_type="buzzheavier"),
            DownloadLink(url="c", host="pixeldrain.com", host_type="pixeldrain"),
        ]
        best = get_best_download_link(links)
        assert best is not None
        assert best.host_type == "buzzheavier"

    def test_skip_hosts(self):
        links = [
            DownloadLink(url="a", host="buzzheavier.com", host_type="buzzheavier"),
            DownloadLink(url="b", host="pixeldrain.com", host_type="pixeldrain"),
        ]
        best = get_best_download_link(links, skip_hosts=["buzzheavier"])
        assert best is not None
        assert best.host_type == "pixeldrain"

    def test_skip_unavailable(self):
        links = [
            DownloadLink(url="a", host="buzzheavier.com", host_type="buzzheavier", is_available=False),
            DownloadLink(url="b", host="pixeldrain.com", host_type="pixeldrain"),
        ]
        best = get_best_download_link(links)
        assert best is not None
        assert best.host_type == "pixeldrain"

    def test_all_unavailable(self):
        links = [
            DownloadLink(url="a", host="mega.nz", host_type="mega", is_available=False),
        ]
        best = get_best_download_link(links)
        assert best is None

    def test_empty_list(self):
        best = get_best_download_link([])
        assert best is None


class TestGetFallbackLinks:
    def test_excludes_failed_host(self):
        links = [
            DownloadLink(url="a", host="mega.nz", host_type="mega"),
            DownloadLink(url="b", host="pixeldrain.com", host_type="pixeldrain"),
            DownloadLink(url="c", host="gofile.io", host_type="gofile"),
        ]
        fallbacks = get_fallback_links(links, "mega")
        assert len(fallbacks) == 2
        assert all(l.host_type != "mega" for l in fallbacks)
        # Should be sorted by priority
        assert fallbacks[0].host_type == "gofile"  # priority 2
        assert fallbacks[1].host_type == "pixeldrain"  # priority 3


class TestMarkLinkUnavailable:
    def test_marks_matching_url(self):
        links = [
            DownloadLink(url="https://mega.nz/abc", host="mega.nz", host_type="mega"),
            DownloadLink(url="https://gofile.io/xyz", host="gofile.io", host_type="gofile"),
        ]
        mark_link_unavailable(links, "https://mega.nz/abc", "404 Not Found")
        assert links[0].is_available is False
        assert links[0].error == "404 Not Found"
        assert links[1].is_available is True

    def test_no_match(self):
        links = [
            DownloadLink(url="https://mega.nz/abc", host="mega.nz", host_type="mega"),
        ]
        mark_link_unavailable(links, "https://nonexistent.com/xyz")
        assert links[0].is_available is True


# ---- Host display info ----

class TestGetHostDisplayInfo:
    def test_known_host(self):
        info = get_host_display_info("buzzheavier")
        assert info["name"] == "Buzzheavier"
        assert info["priority"] == 1
        assert info["has_limit"] is False

    def test_host_with_limits(self):
        info = get_host_display_info("pixeldrain")
        assert info["has_limit"] is True

    def test_unknown_host(self):
        info = get_host_display_info("somenewhoster")
        assert info["name"] == "Somenewhoster"
        assert info["has_limit"] is False


# ---- Platform filtering ----

class TestFilterLinksByPlatform:
    def test_windows_filter(self):
        links = [
            DownloadLink(url="a", host="m", host_type="mega", label="Windows Download"),
            DownloadLink(url="b", host="m", host_type="mega", label="Mac Download"),
            DownloadLink(url="c", host="m", host_type="mega", label="Android APK"),
        ]
        filtered = filter_links_by_platform(links, "windows")
        assert len(filtered) == 1
        assert "Windows" in filtered[0].label

    def test_mac_filter(self):
        links = [
            DownloadLink(url="a", host="m", host_type="mega", label="MacOS Version"),
            DownloadLink(url="b", host="m", host_type="mega", label="Win Version"),
        ]
        filtered = filter_links_by_platform(links, "mac")
        assert len(filtered) == 1
        assert "MacOS" in filtered[0].label

    def test_no_match_returns_all(self):
        links = [
            DownloadLink(url="a", host="m", host_type="mega", label="Download 1"),
            DownloadLink(url="b", host="m", host_type="mega", label="Download 2"),
        ]
        filtered = filter_links_by_platform(links, "linux")
        assert len(filtered) == 2  # All returned when no match


# ---- Download link priority ----

class TestDownloadLinkPriority:
    def test_priority_auto_set(self):
        link = DownloadLink(url="a", host="buzzheavier.com", host_type="buzzheavier")
        assert link.priority == 1

    def test_unknown_host_default_priority(self):
        link = DownloadLink(url="a", host="unknown.com", host_type="unknown")
        assert link.priority == 50


# ---- Thread cache ----

class TestThreadCache:
    def test_cache_and_retrieve(self):
        clear_thread_cache()
        info = ThreadInfo(thread_id=100, url="https://f95zone.to/threads/100/", title="Test")
        cache_thread_info(info)
        cached = get_cached_thread_info(100)
        assert cached is not None
        assert cached.title == "Test"

    def test_cache_miss(self):
        clear_thread_cache()
        assert get_cached_thread_info(99999) is None

    def test_clear_cache(self):
        info = ThreadInfo(thread_id=200, url="test", title="Test")
        cache_thread_info(info)
        clear_thread_cache()
        assert get_cached_thread_info(200) is None

    def test_zero_thread_id_not_cached(self):
        clear_thread_cache()
        info = ThreadInfo(thread_id=0, url="test", title="Test")
        cache_thread_info(info)
        assert get_cached_thread_info(0) is None
