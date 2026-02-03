"""
Centralized configuration management for Game Library Manager.

Provides type-safe, validated configuration with persistence support.

Usage:
    from app.config import get_config, NetworkConfig

    config = get_config()
    timeout = config.network.timeout  # Type-safe access
    config.network.timeout = 60       # Validated assignment
    config.save()                     # Persist to disk
"""

from .app_config import (
    AppConfig,
    NetworkConfig,
    CacheConfig,
    UIConfig,
    DownloadConfig,
    get_config,
    reset_config,
)

__all__ = [
    "AppConfig",
    "NetworkConfig",
    "CacheConfig",
    "UIConfig",
    "DownloadConfig",
    "get_config",
    "reset_config",
]
