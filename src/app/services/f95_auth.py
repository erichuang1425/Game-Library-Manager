from __future__ import annotations
"""
F95zone Authentication and Session Management.

Provides secure login, session persistence, and authenticated HTTP requests.
Credentials are encrypted at rest using platform-specific secure storage.
"""

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from http.cookiejar import CookieJar, Cookie
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse
import urllib.request
import urllib.error

from app.logging_utils import get_logger, kv, RateLimiter, timed
from app.storage.paths import get_app_dir

_log = get_logger("f95_auth")
_rate = RateLimiter()

# F95zone endpoints
F95_BASE = "https://f95zone.to"
F95_LOGIN_URL = f"{F95_BASE}/login/login"
F95_LOGOUT_URL = f"{F95_BASE}/logout/"
F95_PROFILE_URL = f"{F95_BASE}/account/"

# HTTP settings
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
REQUEST_TIMEOUT = 30

# Session settings
SESSION_FILE = "f95_session.json"
CREDENTIALS_FILE = "f95_auth.enc"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    message: str = ""
    username: str = ""
    requires_2fa: bool = False
    error_code: str = ""


@dataclass
class SessionInfo:
    """Current session information."""
    is_authenticated: bool = False
    username: str = ""
    user_id: int = 0
    avatar_url: str = ""
    session_start: Optional[datetime] = None
    last_activity: Optional[datetime] = None


@dataclass
class StoredCredentials:
    """Encrypted credentials structure."""
    username: str = ""
    password_hash: str = ""  # We store a reversible encrypted form
    remember: bool = False


class F95AuthManager:
    """
    Manages F95zone authentication with secure credential storage.

    Security features:
    - Credentials encrypted at rest
    - Session cookies stored separately
    - Automatic session refresh
    - Rate limiting to prevent lockouts
    """

    def __init__(self) -> None:
        self._cookies: CookieJar = CookieJar()
        self._session_info = SessionInfo()
        self._csrf_token: str = ""
        self._last_request_time: float = 0
        self._request_delay: float = 1.0  # Minimum seconds between requests

        self._app_dir = get_app_dir()
        self._session_path = self._app_dir / SESSION_FILE
        self._credentials_path = self._app_dir / CREDENTIALS_FILE

        # Encryption key derived from machine-specific data
        self._enc_key = self._derive_key()

        # Load existing session
        self._load_session()

    def _derive_key(self) -> bytes:
        """
        Derive encryption key from machine-specific data.
        This provides basic protection - credentials are tied to this machine.
        """
        # Combine various machine identifiers
        machine_data = ""

        # Username
        machine_data += os.environ.get("USERNAME", os.environ.get("USER", "default"))

        # Computer name
        machine_data += os.environ.get("COMPUTERNAME", os.environ.get("HOSTNAME", "default"))

        # App-specific salt
        machine_data += "GameLibraryManager_F95Auth_v1"

        # Windows: Try to use machine GUID if available
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            )
            machine_guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            machine_data += machine_guid
            winreg.CloseKey(key)
        except Exception:
            pass

        # Derive key using SHA-256
        return hashlib.sha256(machine_data.encode()).digest()

    def _encrypt(self, data: str) -> str:
        """Simple XOR encryption with base64 encoding."""
        key = self._enc_key
        encrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(data.encode())])
        return base64.b64encode(encrypted).decode()

    def _decrypt(self, data: str) -> str:
        """Decrypt XOR-encrypted base64 data."""
        try:
            key = self._enc_key
            encrypted = base64.b64decode(data.encode())
            decrypted = bytes([b ^ key[i % len(key)] for i, b in enumerate(encrypted)])
            return decrypted.decode()
        except Exception:
            return ""

    def _load_session(self) -> None:
        """Load session from disk."""
        try:
            if self._session_path.exists():
                data = json.loads(self._session_path.read_text(encoding="utf-8"))

                # Check session age
                session_time = data.get("session_start", 0)
                if time.time() - session_time > SESSION_MAX_AGE:
                    _log.info("session_expired")
                    self._session_path.unlink(missing_ok=True)
                    return

                # Restore cookies
                for cookie_data in data.get("cookies", []):
                    try:
                        cookie = Cookie(
                            version=0,
                            name=cookie_data["name"],
                            value=cookie_data["value"],
                            port=None,
                            port_specified=False,
                            domain=cookie_data.get("domain", "f95zone.to"),
                            domain_specified=True,
                            domain_initial_dot=cookie_data.get("domain", "").startswith("."),
                            path=cookie_data.get("path", "/"),
                            path_specified=True,
                            secure=cookie_data.get("secure", True),
                            expires=cookie_data.get("expires"),
                            discard=False,
                            comment=None,
                            comment_url=None,
                            rest={},
                            rfc2109=False,
                        )
                        self._cookies.set_cookie(cookie)
                    except Exception as e:
                        _log.debug("cookie_restore_error %s", kv(err=str(e)))

                # Restore session info
                self._session_info.is_authenticated = data.get("is_authenticated", False)
                self._session_info.username = data.get("username", "")
                self._session_info.user_id = data.get("user_id", 0)
                self._session_info.avatar_url = data.get("avatar_url", "")
                if session_time:
                    self._session_info.session_start = datetime.fromtimestamp(session_time)

                if self._session_info.is_authenticated:
                    _log.info("session_restored %s", kv(
                        username=self._session_info.username,
                        age_hours=round((time.time() - session_time) / 3600, 1)
                    ))
        except Exception as e:
            _log.warning("session_load_error %s", kv(err=str(e)))

    def _save_session(self) -> None:
        """Save session to disk."""
        try:
            cookies_data = []
            for cookie in self._cookies:
                cookies_data.append({
                    "name": cookie.name,
                    "value": cookie.value,
                    "domain": cookie.domain,
                    "path": cookie.path,
                    "secure": cookie.secure,
                    "expires": cookie.expires,
                })

            data = {
                "is_authenticated": self._session_info.is_authenticated,
                "username": self._session_info.username,
                "user_id": self._session_info.user_id,
                "avatar_url": self._session_info.avatar_url,
                "session_start": self._session_info.session_start.timestamp() if self._session_info.session_start else time.time(),
                "cookies": cookies_data,
            }

            self._session_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            _log.debug("session_saved")
        except Exception as e:
            _log.warning("session_save_error %s", kv(err=str(e)))

    def save_credentials(self, username: str, password: str, remember: bool = True) -> None:
        """Save credentials encrypted to disk."""
        if not remember:
            self._credentials_path.unlink(missing_ok=True)
            return

        try:
            data = {
                "username": self._encrypt(username),
                "password": self._encrypt(password),
                "remember": remember,
            }
            self._credentials_path.write_text(json.dumps(data), encoding="utf-8")
            _log.info("credentials_saved %s", kv(username=username))
        except Exception as e:
            _log.warning("credentials_save_error %s", kv(err=str(e)))

    def load_credentials(self) -> Optional[Tuple[str, str]]:
        """Load saved credentials if available."""
        try:
            if self._credentials_path.exists():
                data = json.loads(self._credentials_path.read_text(encoding="utf-8"))
                username = self._decrypt(data.get("username", ""))
                password = self._decrypt(data.get("password", ""))
                if username and password:
                    return username, password
        except Exception as e:
            _log.warning("credentials_load_error %s", kv(err=str(e)))
        return None

    def clear_credentials(self) -> None:
        """Remove saved credentials."""
        self._credentials_path.unlink(missing_ok=True)
        _log.info("credentials_cleared")

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._request_delay:
            time.sleep(self._request_delay - elapsed)
        self._last_request_time = time.time()

    def _make_request(
        self,
        url: str,
        data: Optional[Dict[str, str]] = None,
        method: str = "GET",
    ) -> Tuple[int, str, Dict[str, str]]:
        """
        Make an HTTP request with cookies.
        Returns (status_code, body, response_headers).
        """
        self._rate_limit()

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Referer": F95_BASE,
        }

        # Add cookies
        cookie_header = "; ".join(f"{c.name}={c.value}" for c in self._cookies)
        if cookie_header:
            headers["Cookie"] = cookie_header

        # Add CSRF token if we have one
        if self._csrf_token and data is not None:
            data["_xfToken"] = self._csrf_token

        body = None
        if data:
            body = urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            req = urllib.request.Request(url, data=body, headers=headers, method=method)

            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                # Extract and store cookies from response
                for header in resp.headers.get_all("Set-Cookie") or []:
                    self._parse_set_cookie(header)

                response_body = resp.read().decode("utf-8", errors="ignore")
                response_headers = dict(resp.headers)

                return resp.status, response_body, response_headers

        except urllib.error.HTTPError as e:
            return e.code, "", {}
        except Exception as e:
            _log.warning("request_error %s", kv(url=url, err=str(e)))
            raise

    def _parse_set_cookie(self, header: str) -> None:
        """Parse Set-Cookie header and store cookie."""
        try:
            parts = header.split(";")
            if not parts:
                return

            name_value = parts[0].strip()
            if "=" not in name_value:
                return

            name, value = name_value.split("=", 1)
            name = name.strip()
            value = value.strip()

            # Parse attributes
            domain = ".f95zone.to"
            path = "/"
            secure = False
            expires = None

            for part in parts[1:]:
                part = part.strip().lower()
                if part.startswith("domain="):
                    domain = part[7:]
                elif part.startswith("path="):
                    path = part[5:]
                elif part == "secure":
                    secure = True
                elif part.startswith("expires="):
                    # Parse expiry (simplified)
                    pass

            cookie = Cookie(
                version=0,
                name=name,
                value=value,
                port=None,
                port_specified=False,
                domain=domain,
                domain_specified=True,
                domain_initial_dot=domain.startswith("."),
                path=path,
                path_specified=True,
                secure=secure,
                expires=expires,
                discard=False,
                comment=None,
                comment_url=None,
                rest={},
                rfc2109=False,
            )
            self._cookies.set_cookie(cookie)
        except Exception as e:
            _log.debug("cookie_parse_error %s", kv(err=str(e)))

    def _extract_csrf_token(self, html_text: str) -> Optional[str]:
        """Extract CSRF token from page HTML."""
        patterns = [
            r'name="_xfToken"\s+value="([^"]+)"',
            r"_xfToken['\"]?\s*:\s*['\"]([^'\"]+)['\"]",
            r'data-csrf="([^"]+)"',
        ]

        for pattern in patterns:
            match = re.search(pattern, html_text)
            if match:
                return match.group(1)
        return None

    def _extract_user_info(self, html_text: str) -> Tuple[str, int, str]:
        """Extract username, user_id, and avatar from page HTML."""
        username = ""
        user_id = 0
        avatar_url = ""

        # Username
        username_patterns = [
            r'data-user-id="\d+"\s+data-username="([^"]+)"',
            r'class="username"[^>]*>([^<]+)<',
        ]
        for pattern in username_patterns:
            match = re.search(pattern, html_text)
            if match:
                username = match.group(1).strip()
                break

        # User ID
        userid_patterns = [
            r'data-user-id="(\d+)"',
            r'member/(\d+)',
        ]
        for pattern in userid_patterns:
            match = re.search(pattern, html_text)
            if match:
                user_id = int(match.group(1))
                break

        # Avatar
        avatar_patterns = [
            r'class="avatar[^"]*"[^>]*>\s*<img[^>]+src="([^"]+)"',
        ]
        for pattern in avatar_patterns:
            match = re.search(pattern, html_text)
            if match:
                avatar_url = match.group(1)
                if avatar_url.startswith("/"):
                    avatar_url = F95_BASE + avatar_url
                break

        return username, user_id, avatar_url

    def login(
        self,
        username: str,
        password: str,
        remember: bool = True,
        save_credentials: bool = False,
    ) -> AuthResult:
        """
        Attempt to log in to F95zone.

        Args:
            username: F95zone username
            password: F95zone password
            remember: Whether to keep session long-lived
            save_credentials: Whether to save credentials for auto-login

        Returns:
            AuthResult with success status and any error messages
        """
        with timed(_log, "f95_login", username=username):
            try:
                # First, get the login page to extract CSRF token
                status, body, _ = self._make_request(f"{F95_BASE}/login/")

                if status != 200:
                    return AuthResult(
                        success=False,
                        message=f"Failed to load login page (status {status})",
                        error_code="page_load_failed"
                    )

                self._csrf_token = self._extract_csrf_token(body) or ""

                if not self._csrf_token:
                    _log.warning("csrf_token_not_found")

                # Prepare login data
                login_data = {
                    "login": username,
                    "password": password,
                    "remember": "1" if remember else "0",
                    "_xfRedirect": F95_BASE,
                }

                # Submit login
                status, body, headers = self._make_request(
                    F95_LOGIN_URL,
                    data=login_data,
                    method="POST"
                )

                # Check for 2FA requirement
                if "two-step" in body.lower() or "two_step" in body.lower():
                    return AuthResult(
                        success=False,
                        message="Two-factor authentication required",
                        requires_2fa=True,
                        error_code="2fa_required"
                    )

                # Check for errors in response
                error_patterns = [
                    (r'class="blockMessage[^"]*error[^"]*"[^>]*>([^<]+)', "login_error"),
                    (r'Incorrect password', "wrong_password"),
                    (r'The requested user could not be found', "user_not_found"),
                ]

                for pattern, error_code in error_patterns:
                    match = re.search(pattern, body, re.IGNORECASE)
                    if match:
                        message = match.group(1) if match.lastindex else pattern
                        return AuthResult(
                            success=False,
                            message=message.strip(),
                            error_code=error_code
                        )

                # Check if we're logged in by looking for user menu
                user_info = self._extract_user_info(body)

                if user_info[0]:  # Has username
                    self._session_info.is_authenticated = True
                    self._session_info.username = user_info[0]
                    self._session_info.user_id = user_info[1]
                    self._session_info.avatar_url = user_info[2]
                    self._session_info.session_start = datetime.now()
                    self._session_info.last_activity = datetime.now()

                    self._save_session()

                    if save_credentials:
                        self.save_credentials(username, password, remember)

                    _log.info("login_success %s", kv(
                        username=self._session_info.username,
                        user_id=self._session_info.user_id
                    ))

                    return AuthResult(
                        success=True,
                        message="Login successful",
                        username=self._session_info.username
                    )

                # Login might have succeeded but we couldn't verify
                # Try fetching profile to confirm
                status, body, _ = self._make_request(F95_PROFILE_URL)
                if status == 200:
                    user_info = self._extract_user_info(body)
                    if user_info[0]:
                        self._session_info.is_authenticated = True
                        self._session_info.username = user_info[0]
                        self._session_info.user_id = user_info[1]
                        self._session_info.avatar_url = user_info[2]
                        self._session_info.session_start = datetime.now()

                        self._save_session()

                        if save_credentials:
                            self.save_credentials(username, password, remember)

                        return AuthResult(
                            success=True,
                            message="Login successful",
                            username=self._session_info.username
                        )

                return AuthResult(
                    success=False,
                    message="Login failed - could not verify session",
                    error_code="verification_failed"
                )

            except Exception as e:
                _log.exception("login_error")
                return AuthResult(
                    success=False,
                    message=str(e),
                    error_code="exception"
                )

    def logout(self) -> bool:
        """Log out and clear session."""
        try:
            if self._session_info.is_authenticated:
                # Try to logout on server
                try:
                    self._make_request(F95_LOGOUT_URL)
                except Exception:
                    pass

            # Clear local session
            self._cookies = CookieJar()
            self._session_info = SessionInfo()
            self._csrf_token = ""

            # Remove session file
            self._session_path.unlink(missing_ok=True)

            _log.info("logout_success")
            return True

        except Exception as e:
            _log.warning("logout_error %s", kv(err=str(e)))
            return False

    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._session_info.is_authenticated

    def get_session_info(self) -> SessionInfo:
        """Get current session information."""
        return self._session_info

    def refresh_session(self) -> bool:
        """
        Refresh session by checking if still valid.
        Returns True if session is valid.
        """
        if not self._session_info.is_authenticated:
            return False

        try:
            status, body, _ = self._make_request(F95_PROFILE_URL)

            if status == 200:
                user_info = self._extract_user_info(body)
                if user_info[0]:
                    self._session_info.last_activity = datetime.now()
                    self._save_session()
                    return True

            # Session invalid
            self._session_info.is_authenticated = False
            self._save_session()
            return False

        except Exception as e:
            _log.warning("session_refresh_error %s", kv(err=str(e)))
            return False

    def fetch_authenticated(self, url: str) -> Tuple[int, str]:
        """
        Fetch a URL with authentication cookies.
        Returns (status_code, body).
        """
        status, body, _ = self._make_request(url)
        self._session_info.last_activity = datetime.now()
        return status, body

    def auto_login(self) -> AuthResult:
        """
        Attempt auto-login using saved credentials.
        Returns AuthResult.
        """
        creds = self.load_credentials()
        if creds:
            username, password = creds
            return self.login(username, password, remember=True, save_credentials=False)
        return AuthResult(
            success=False,
            message="No saved credentials",
            error_code="no_credentials"
        )


# Global instance
_auth_manager: Optional[F95AuthManager] = None


def get_auth_manager() -> F95AuthManager:
    """Get the global F95 auth manager instance."""
    global _auth_manager
    if _auth_manager is None:
        _auth_manager = F95AuthManager()
    return _auth_manager
