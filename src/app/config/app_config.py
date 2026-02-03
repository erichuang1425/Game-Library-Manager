"""
Application configuration with type-safe access and validation.

Provides centralized configuration management with:
- Dataclass-based configuration sections
- Type validation on assignment
- Default values for all settings
- Persistence to JSON file
- Change notification via event bus
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logging_utils import get_logger, kv
from app.storage.paths import get_app_dir

_log = get_logger("config")


@dataclass
class NetworkConfig:
    """Network-related configuration."""

    timeout: int = 30
    """Default timeout in seconds for HTTP requests."""

    extended_timeout: int = 120
    """Extended timeout for long operations (downloads, etc.)."""

    max_retries: int = 3
    """Maximum number of retry attempts for failed requests."""

    retry_delay: float = 1.5
    """Delay in seconds between retry attempts."""

    chunk_size: int = 8192
    """Chunk size in bytes for streaming downloads."""

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    """User-Agent string for HTTP requests."""

    def __post_init__(self):
        """Validate configuration values."""
        if self.timeout < 1:
            self.timeout = 1
        if self.extended_timeout < self.timeout:
            self.extended_timeout = self.timeout
        if self.max_retries < 0:
            self.max_retries = 0
        if self.retry_delay < 0:
            self.retry_delay = 0
        if self.chunk_size < 1024:
            self.chunk_size = 1024


@dataclass
class CacheConfig:
    """Cache-related configuration."""

    html_cache_ttl: int = 6 * 60 * 60
    """TTL for HTML content cache in seconds (default: 6 hours)."""

    version_cache_ttl: int = 24 * 60 * 60
    """TTL for parsed version cache in seconds (default: 24 hours)."""

    max_html_cache_entries: int = 100
    """Maximum entries in HTML cache."""

    max_version_cache_entries: int = 200
    """Maximum entries in version cache."""

    max_icon_cache_entries: int = 500
    """Maximum entries in icon cache."""

    search_cache_enabled: bool = True
    """Enable search haystack caching."""

    max_search_cache_entries: int = 2000
    """Maximum entries in search cache."""

    def __post_init__(self):
        """Validate configuration values."""
        if self.html_cache_ttl < 60:
            self.html_cache_ttl = 60
        if self.max_html_cache_entries < 10:
            self.max_html_cache_entries = 10


@dataclass
class UIConfig:
    """UI-related configuration."""

    theme: str = "dark"
    """Current theme (dark, light, custom)."""

    view_mode: str = "comfortable"
    """Grid view mode (comfortable, compact)."""

    font_family: str = "Segoe UI"
    """Font family for the UI."""

    font_scale: float = 1.0
    """Font scale multiplier."""

    details_on_launch: bool = False
    """Show details panel when launching a game."""

    details_on_selection: bool = True
    """Show details panel when selecting a game."""

    focus_mode: bool = False
    """Enable focus mode (hide sidebar and details)."""

    show_sidebar: bool = True
    """Show the sidebar."""

    show_status_bar: bool = True
    """Show the status bar."""

    sidebar_width_pct: int = 15
    """Sidebar width as percentage of window width."""

    details_width_pct: int = 25
    """Details panel width as percentage of window width."""

    def __post_init__(self):
        """Validate configuration values."""
        if self.font_scale < 0.5:
            self.font_scale = 0.5
        if self.font_scale > 2.0:
            self.font_scale = 2.0
        if self.theme not in ("dark", "light", "custom"):
            self.theme = "dark"
        if self.view_mode not in ("comfortable", "compact"):
            self.view_mode = "comfortable"


@dataclass
class DownloadConfig:
    """Download-related configuration."""

    max_concurrent: int = 2
    """Maximum concurrent downloads."""

    default_download_dir: str = ""
    """Default download directory (empty = ~/Downloads/GameLibraryManager)."""

    auto_extract: bool = True
    """Automatically extract downloaded archives."""

    delete_archive_after_extract: bool = False
    """Delete archive after successful extraction."""

    common_passwords: List[str] = field(default_factory=lambda: [
        "f95zone",
        "f95",
        "www.f95zone.to",
    ])
    """Common passwords to try for encrypted archives."""

    def __post_init__(self):
        """Validate configuration values."""
        if self.max_concurrent < 1:
            self.max_concurrent = 1
        if self.max_concurrent > 10:
            self.max_concurrent = 10


@dataclass
class AppConfig:
    """
    Central application configuration.

    Contains all configuration sections with type-safe access.
    """

    network: NetworkConfig = field(default_factory=NetworkConfig)
    """Network configuration section."""

    cache: CacheConfig = field(default_factory=CacheConfig)
    """Cache configuration section."""

    ui: UIConfig = field(default_factory=UIConfig)
    """UI configuration section."""

    download: DownloadConfig = field(default_factory=DownloadConfig)
    """Download configuration section."""

    # Application paths
    data_dir: str = ""
    """Application data directory (empty = default)."""

    games_folder: str = ""
    """Default games installation folder."""

    shortcuts_folder: str = ""
    """Default shortcuts folder."""

    # Feature flags
    debug_mode: bool = False
    """Enable debug features."""

    telemetry_enabled: bool = False
    """Enable anonymous telemetry (not implemented)."""

    _config_path: Path = field(default=None, repr=False)
    """Path to configuration file."""

    def __post_init__(self):
        """Initialize configuration."""
        if self._config_path is None:
            self._config_path = get_app_dir() / "config.json"

        if not self.data_dir:
            self.data_dir = str(get_app_dir())

        if not self.games_folder:
            self.games_folder = str(Path.home() / "Games")

        if not self.shortcuts_folder:
            self.shortcuts_folder = str(Path.home() / "Shortcuts")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        data = {
            "network": asdict(self.network),
            "cache": asdict(self.cache),
            "ui": asdict(self.ui),
            "download": asdict(self.download),
            "data_dir": self.data_dir,
            "games_folder": self.games_folder,
            "shortcuts_folder": self.shortcuts_folder,
            "debug_mode": self.debug_mode,
            "telemetry_enabled": self.telemetry_enabled,
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any], config_path: Optional[Path] = None) -> "AppConfig":
        """Create configuration from dictionary."""
        config = cls(_config_path=config_path)

        # Load network config
        if "network" in data:
            config.network = NetworkConfig(**data["network"])

        # Load cache config
        if "cache" in data:
            config.cache = CacheConfig(**data["cache"])

        # Load UI config
        if "ui" in data:
            config.ui = UIConfig(**data["ui"])

        # Load download config
        if "download" in data:
            dl_data = data["download"]
            # Handle list field specially
            if "common_passwords" not in dl_data:
                dl_data["common_passwords"] = DownloadConfig().common_passwords
            config.download = DownloadConfig(**dl_data)

        # Load simple fields
        if "data_dir" in data:
            config.data_dir = data["data_dir"]
        if "games_folder" in data:
            config.games_folder = data["games_folder"]
        if "shortcuts_folder" in data:
            config.shortcuts_folder = data["shortcuts_folder"]
        if "debug_mode" in data:
            config.debug_mode = data["debug_mode"]
        if "telemetry_enabled" in data:
            config.telemetry_enabled = data["telemetry_enabled"]

        return config

    def save(self) -> None:
        """Save configuration to disk."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            data = self.to_dict()
            self._config_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            _log.info("config_saved %s", kv(path=str(self._config_path)))

            # Emit event if event bus is available
            try:
                from app.events import Event, emit
                emit(Event.SETTINGS_CHANGED, self)
            except ImportError:
                pass

        except Exception as e:
            _log.error("config_save_failed %s", kv(
                path=str(self._config_path),
                error=str(e)
            ))

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> "AppConfig":
        """
        Load configuration from disk.

        Args:
            config_path: Path to config file (uses default if not provided)

        Returns:
            Loaded configuration or default if file doesn't exist
        """
        if config_path is None:
            config_path = get_app_dir() / "config.json"

        try:
            if config_path.exists():
                data = json.loads(config_path.read_text(encoding="utf-8"))
                config = cls.from_dict(data, config_path)
                _log.info("config_loaded %s", kv(path=str(config_path)))
                return config
        except Exception as e:
            _log.warning("config_load_failed %s", kv(
                path=str(config_path),
                error=str(e)
            ))

        # Return default configuration
        return cls(_config_path=config_path)

    def reset_to_defaults(self) -> None:
        """Reset all configuration to default values."""
        default = AppConfig(_config_path=self._config_path)
        self.network = default.network
        self.cache = default.cache
        self.ui = default.ui
        self.download = default.download
        self.debug_mode = default.debug_mode
        self.telemetry_enabled = default.telemetry_enabled
        _log.info("config_reset_to_defaults")


# Global instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig.load()
    return _config


def reset_config() -> AppConfig:
    """Reset and reload configuration."""
    global _config
    _config = AppConfig.load()
    return _config
