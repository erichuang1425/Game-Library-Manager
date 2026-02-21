"""Tests for version_parser.py — parametrized pytest version."""
import pytest
from app.services.version_parser import (
    parse_version, compare_versions, CompareResult, VersionKind,
)


class TestParseVersion:
    @pytest.mark.parametrize("raw,expected_kind", [
        ("0.1.1", VersionKind.NUMERIC),
        ("0.01 Fixed", VersionKind.NUMERIC),
        ("0.1.1a - Patreon", VersionKind.NUMERIC),
        ("Version: v0.6", VersionKind.NUMERIC),
        ("Ver 1.0", VersionKind.NUMERIC),
        ("build 38.2", VersionKind.BUILD),
        ("Season 2 - Redux Demo", VersionKind.SEASON),
    ])
    def test_parse_formats(self, raw, expected_kind):
        vi = parse_version(raw)
        assert vi is not None
        assert vi.kind == expected_kind

    def test_parse_empty_string(self):
        vi = parse_version("")
        assert vi.kind == VersionKind.UNKNOWN

    def test_parse_preserves_raw(self):
        vi = parse_version("0.1.1a - Patreon")
        assert vi.raw == "0.1.1a - Patreon"

    def test_parse_suffix_letter(self):
        vi = parse_version("0.1.1a")
        assert vi.suffix_letter == "a"

    def test_numeric_str(self):
        vi = parse_version("0.1.1")
        assert vi.numeric_str == "0.1.1"


class TestCompareVersions:
    @pytest.mark.parametrize("a,b,expected", [
        ("0.1.0", "0.1.1", CompareResult.OLDER),
        ("0.1.1", "0.1.0", CompareResult.NEWER),
        ("0.1.1a", "0.1.1b", CompareResult.OLDER),
        ("Season 2", "Season 2", CompareResult.SAME),
        ("1.0", "1.0", CompareResult.SAME),
        ("build 10", "build 20", CompareResult.OLDER),
    ])
    def test_comparisons(self, a, b, expected):
        va = parse_version(a)
        vb = parse_version(b)
        assert compare_versions(va, vb) == expected

    def test_unknown_versions(self):
        a = parse_version("demo")
        b = parse_version("patreon")
        assert compare_versions(a, b) == CompareResult.UNKNOWN
