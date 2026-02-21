"""Custom exception hierarchy for Game Library Manager.

This module provides a structured exception hierarchy to replace generic
Exception catches throughout the codebase. All application exceptions
inherit from AppError, enabling targeted error handling and better
error reporting.

Usage:
    from app.exceptions import NetworkError, StorageError, ParseError

    try:
        # ... network operation ...
    except NetworkError as e:
        if e.retriable:
            # Retry logic
        else:
            # Handle permanent error
"""

from __future__ import annotations
from typing import Optional


class AppError(Exception):
    """Base exception for all application errors.

    All custom exceptions in the application should inherit from this class.
    This allows catching all app-specific errors with a single except clause
    while letting system exceptions (KeyboardInterrupt, SystemExit) propagate.
    """
    pass


class StorageError(AppError):
    """Errors related to file I/O, JSON parsing, and path resolution.

    Examples:
        - Failed to read/write library.json
        - Invalid JSON format
        - Missing or corrupted settings file
        - Path resolution failures
        - Permission errors accessing app data directory
    """

    def __init__(self, message: str, path: Optional[str] = None, cause: Optional[Exception] = None):
        self.path = path
        self.cause = cause
        if path:
            super().__init__(f"{message} (path: {path})")
        else:
            super().__init__(message)


class NetworkError(AppError):
    """Errors related to HTTP requests, timeouts, and DNS resolution.

    Examples:
        - Connection timeout
        - DNS resolution failure
        - HTTP 4xx/5xx errors
        - SSL/TLS errors
        - Redirect loops

    Attributes:
        url: The URL that failed
        reason: Human-readable error reason
        retriable: Whether the operation can be retried
        status_code: HTTP status code if applicable
    """

    def __init__(
        self,
        url: str,
        reason: str,
        retriable: bool = False,
        status_code: Optional[int] = None,
    ):
        self.url = url
        self.reason = reason
        self.retriable = retriable
        self.status_code = status_code

        msg = f"Network error for {url}: {reason}"
        if status_code:
            msg = f"Network error for {url} (HTTP {status_code}): {reason}"
        super().__init__(msg)


class ParseError(AppError):
    """Errors related to version parsing, HTML parsing, and data extraction.

    Examples:
        - Invalid version string format
        - Malformed HTML/XML
        - Missing required HTML elements
        - Invalid date/time format
        - Unexpected data structure
    """

    def __init__(self, message: str, data: Optional[str] = None):
        self.data = data
        if data and len(data) < 100:
            super().__init__(f"{message} (data: {data})")
        else:
            super().__init__(message)


class LaunchError(AppError):
    """Errors related to game launching and shortcut resolution.

    Examples:
        - Shortcut target not found
        - Invalid shortcut format
        - Failed to parse .lnk file
        - Executable not found
        - Permission denied on launch
    """

    def __init__(self, message: str, game_title: Optional[str] = None, path: Optional[str] = None):
        self.game_title = game_title
        self.path = path

        details = []
        if game_title:
            details.append(f"game: {game_title}")
        if path:
            details.append(f"path: {path}")

        if details:
            super().__init__(f"{message} ({', '.join(details)})")
        else:
            super().__init__(message)


class AuthError(NetworkError):
    """Errors related to authentication and session management.

    Examples:
        - Invalid credentials
        - Session expired
        - Login required
        - 2FA required
        - Account locked
        - CAPTCHA challenge

    This inherits from NetworkError since authentication errors
    typically occur during network operations.
    """

    def __init__(self, url: str, reason: str, requires_login: bool = True):
        self.requires_login = requires_login
        # Auth errors are typically retriable after user intervention
        super().__init__(url, reason, retriable=requires_login, status_code=401)


class ValidationError(AppError):
    """Errors related to data validation.

    Examples:
        - Invalid game ID format
        - Missing required field
        - Value out of range
        - Invalid enum value
        - Type mismatch
    """

    def __init__(self, message: str, field: Optional[str] = None, value: Optional[str] = None):
        self.field = field
        self.value = value

        if field:
            super().__init__(f"Validation error for {field}: {message}")
        else:
            super().__init__(f"Validation error: {message}")
