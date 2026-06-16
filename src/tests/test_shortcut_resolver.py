from pathlib import Path

from app.services.shortcut_resolver import (
    NullShellLinkAdapter,
    ResolvedShortcut,
    default_shell_link_adapter,
    resolve_lnk,
    resolve_shortcut_any,
    resolve_url,
)


class FakeShellLinkAdapter:
    def resolve(self, lnk_path: Path) -> ResolvedShortcut:
        return ResolvedShortcut(
            target_path=str(lnk_path.with_suffix(".exe")),
            args="--fullscreen",
            working_dir=str(lnk_path.parent),
        )


class BrokenShellLinkAdapter:
    def resolve(self, lnk_path: Path) -> ResolvedShortcut:
        raise OSError("COM failure")


def test_default_adapter_is_portable_on_non_windows():
    # The default adapter must be safe to create on Linux/macOS CI, where
    # pywin32 is unavailable, while Windows CI exercises the pywin32 path.
    adapter = default_shell_link_adapter()
    assert hasattr(adapter, "resolve")


def test_null_adapter_returns_empty_result():
    assert NullShellLinkAdapter().resolve(Path("game.lnk")) == ResolvedShortcut()


def test_resolve_lnk_uses_injected_adapter(tmp_path):
    lnk = tmp_path / "Game.lnk"
    lnk.write_text("placeholder", encoding="utf-8")

    resolved = resolve_lnk(lnk, adapter=FakeShellLinkAdapter())

    assert resolved.target_path == str(tmp_path / "Game.exe")
    assert resolved.args == "--fullscreen"
    assert resolved.working_dir == str(tmp_path)


def test_resolve_lnk_failure_returns_empty_result(tmp_path):
    assert (
        resolve_lnk(tmp_path / "bad.lnk", adapter=BrokenShellLinkAdapter())
        == ResolvedShortcut()
    )


def test_resolve_shortcut_any_passes_adapter_for_lnk(tmp_path):
    resolved = resolve_shortcut_any(
        tmp_path / "Game.lnk", adapter=FakeShellLinkAdapter()
    )
    assert resolved.target_path.endswith("Game.exe")


def test_resolve_url_reads_url_value(tmp_path):
    url_file = tmp_path / "Game.url"
    url_file.write_text(
        "[InternetShortcut]\nURL=https://example.test/game\n", encoding="utf-8"
    )

    assert resolve_url(url_file).url == "https://example.test/game"
