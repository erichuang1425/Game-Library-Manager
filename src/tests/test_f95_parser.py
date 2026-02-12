"""Tests for f95_parser.py - version extraction from F95zone thread HTML."""
import pytest
from app.services.f95_parser import extract_f95_version


def _make_html(body_content: str, title: str = "Test Thread") -> str:
    """Helper to build minimal F95zone-like HTML."""
    return f"""
    <html>
    <head><title>{title}</title></head>
    <body>
    <div class="p-title"><h1>{title}</h1></div>
    <article class="message">
      <div class="message-content">
        <div class="bbWrapper">
          {body_content}
        </div>
      </div>
    </article>
    </body>
    </html>
    """


class TestExtractF95VersionXPath:
    """Tests for pass 1 - xpath_header extraction."""

    def test_version_keyword(self):
        html = _make_html("<p>Version: 0.5.2</p>")
        ver, method = extract_f95_version(html)
        assert ver == "0.5.2"
        assert method == "xpath_header"

    def test_ver_keyword(self):
        html = _make_html("<p>Ver 1.0.3</p>")
        ver, method = extract_f95_version(html)
        assert ver == "1.0.3"
        assert method == "xpath_header"

    def test_v_prefix(self):
        html = _make_html("<p>v2.1</p>")
        ver, method = extract_f95_version(html)
        assert ver == "2.1"
        assert method == "xpath_header"

    def test_build_keyword(self):
        html = _make_html("<p>Build 38.2</p>")
        ver, method = extract_f95_version(html)
        assert ver == "38.2"
        assert method == "xpath_header"

    def test_season_keyword(self):
        html = _make_html("<p>Season 2 - Redux Demo</p>")
        ver, method = extract_f95_version(html)
        assert ver == "2 - Redux Demo"
        assert method == "xpath_header"

    def test_version_with_colon(self):
        html = _make_html("<p>Version: v0.6</p>")
        ver, method = extract_f95_version(html)
        assert ver == "v0.6"
        assert method == "xpath_header"

    def test_version_with_dash(self):
        html = _make_html("<p>Version- 3.0 Alpha</p>")
        ver, method = extract_f95_version(html)
        assert ver == "3.0 Alpha"
        assert method == "xpath_header"

    def test_case_insensitive(self):
        html = _make_html("<p>VERSION 1.2</p>")
        ver, method = extract_f95_version(html)
        assert ver == "1.2"
        assert method == "xpath_header"


class TestExtractF95VersionLineScan:
    """Tests for pass 2 - line_scan extraction."""

    def test_version_in_article_body(self):
        # Content not in message-content/bbWrapper but in article
        html = """
        <html><body>
        <article class="message">
          <p>Some intro text</p>
          <p>Version: 0.3.1</p>
        </article>
        </body></html>
        """
        ver, method = extract_f95_version(html)
        assert ver is not None
        assert "0.3.1" in ver

    def test_multiline_body_version(self):
        html = """
        <html><body>
        <article class="message">
          <div>Overview: A great game
Developer: TestDev
Version: 1.5.0
Updated: 2024-01-01</div>
        </article>
        </body></html>
        """
        ver, method = extract_f95_version(html)
        assert ver is not None
        assert "1.5.0" in ver


class TestExtractF95VersionNone:
    """Tests for when no version can be found."""

    def test_empty_html(self):
        ver, method = extract_f95_version("<html><body></body></html>")
        assert ver is None
        assert method == "none"

    def test_no_version_text(self):
        html = _make_html("<p>This game is amazing, download it now!</p>")
        ver, method = extract_f95_version(html)
        assert ver is None
        assert method == "none"

    def test_minimal_html(self):
        ver, method = extract_f95_version("<html></html>")
        assert ver is None
        assert method == "none"


class TestExtractF95VersionEdgeCases:
    """Edge case tests."""

    def test_version_with_suffix_letter(self):
        html = _make_html("<p>Version 0.1.1a - Patreon</p>")
        ver, method = extract_f95_version(html)
        assert ver is not None
        assert "0.1.1a" in ver

    def test_version_with_fixed_suffix(self):
        html = _make_html("<p>Version 0.01 Fixed</p>")
        ver, method = extract_f95_version(html)
        assert ver is not None
        assert "0.01" in ver

    def test_version_first_match_wins(self):
        """First version match in XPath should be returned."""
        html = _make_html("<p>Version: 1.0</p><p>Version: 2.0</p>")
        ver, method = extract_f95_version(html)
        assert ver == "1.0"

    def test_version_with_whitespace(self):
        html = _make_html("<p>  Version:   3.2.1  </p>")
        ver, method = extract_f95_version(html)
        assert ver == "3.2.1"
