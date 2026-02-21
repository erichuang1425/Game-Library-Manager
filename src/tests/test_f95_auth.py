"""Tests for f95_auth.py - F95zone authentication and session management."""
import json
import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from app.services.f95_auth import (
    F95AuthManager,
    AuthResult,
    SessionInfo,
    StoredCredentials,
    F95_BASE,
    F95_LOGIN_URL,
    SESSION_MAX_AGE,
)


@pytest.fixture
def temp_app_dir(tmp_path):
    """Provide a temporary app directory for tests."""
    return tmp_path


@pytest.fixture
def auth_manager(temp_app_dir):
    """Create an F95AuthManager with a temp directory."""
    with patch("app.services.f95_auth.get_app_dir", return_value=temp_app_dir):
        mgr = F95AuthManager()
    return mgr


# ---- Encryption / Decryption ----

class TestEncryptDecrypt:
    def test_roundtrip(self, auth_manager):
        original = "hello_world_password123"
        encrypted = auth_manager._encrypt(original)
        decrypted = auth_manager._decrypt(encrypted)
        assert decrypted == original

    def test_encrypted_differs_from_original(self, auth_manager):
        original = "secret"
        encrypted = auth_manager._encrypt(original)
        assert encrypted != original

    def test_empty_string(self, auth_manager):
        encrypted = auth_manager._encrypt("")
        decrypted = auth_manager._decrypt(encrypted)
        assert decrypted == ""

    def test_unicode_characters(self, auth_manager):
        original = "p\u00e4ssw\u00f6rd_\u00fc\u00df"
        encrypted = auth_manager._encrypt(original)
        decrypted = auth_manager._decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_invalid_data(self, auth_manager):
        result = auth_manager._decrypt("not-valid-base64!!!")
        assert result == ""


# ---- Key derivation ----

class TestKeyDerivation:
    def test_key_is_bytes(self, auth_manager):
        assert isinstance(auth_manager._enc_key, bytes)

    def test_key_length_sha256(self, auth_manager):
        assert len(auth_manager._enc_key) == 32  # SHA-256 = 32 bytes

    def test_key_deterministic(self, temp_app_dir):
        """Same environment should produce same key."""
        with patch("app.services.f95_auth.get_app_dir", return_value=temp_app_dir):
            mgr1 = F95AuthManager()
            mgr2 = F95AuthManager()
        assert mgr1._enc_key == mgr2._enc_key


# ---- Credential storage ----

class TestCredentialStorage:
    def test_save_and_load(self, auth_manager):
        auth_manager.save_credentials("testuser", "testpass123")
        result = auth_manager.load_credentials()
        assert result is not None
        username, password = result
        assert username == "testuser"
        assert password == "testpass123"

    def test_load_without_save(self, auth_manager):
        result = auth_manager.load_credentials()
        assert result is None

    def test_save_remember_false_deletes(self, auth_manager):
        auth_manager.save_credentials("testuser", "testpass123")
        auth_manager.save_credentials("testuser", "testpass123", remember=False)
        result = auth_manager.load_credentials()
        assert result is None

    def test_clear_credentials(self, auth_manager):
        auth_manager.save_credentials("testuser", "testpass123")
        auth_manager.clear_credentials()
        result = auth_manager.load_credentials()
        assert result is None

    def test_credentials_file_encrypted(self, auth_manager):
        auth_manager.save_credentials("testuser", "testpass123")
        # Read raw file - should not contain plaintext credentials
        raw = auth_manager._credentials_path.read_text()
        assert "testpass123" not in raw
        assert "testuser" not in raw


# ---- Session storage ----

class TestSessionStorage:
    def test_save_and_load_session(self, temp_app_dir):
        with patch("app.services.f95_auth.get_app_dir", return_value=temp_app_dir):
            mgr = F95AuthManager()
            mgr._session_info.is_authenticated = True
            mgr._session_info.username = "testuser"
            mgr._session_info.user_id = 12345
            from datetime import datetime
            mgr._session_info.session_start = datetime.now()
            mgr._save_session()

        # Load in a new instance
        with patch("app.services.f95_auth.get_app_dir", return_value=temp_app_dir):
            mgr2 = F95AuthManager()

        assert mgr2._session_info.is_authenticated is True
        assert mgr2._session_info.username == "testuser"
        assert mgr2._session_info.user_id == 12345

    def test_expired_session_discarded(self, temp_app_dir):
        import time
        with patch("app.services.f95_auth.get_app_dir", return_value=temp_app_dir):
            mgr = F95AuthManager()

        # Write a session with old timestamp
        session_data = {
            "is_authenticated": True,
            "username": "olduser",
            "user_id": 111,
            "avatar_url": "",
            "session_start": time.time() - SESSION_MAX_AGE - 3600,  # Expired
            "cookies": [],
        }
        (temp_app_dir / "f95_session.json").write_text(json.dumps(session_data))

        # New manager should not load expired session
        with patch("app.services.f95_auth.get_app_dir", return_value=temp_app_dir):
            mgr2 = F95AuthManager()
        assert mgr2._session_info.is_authenticated is False

    def test_no_session_file(self, auth_manager):
        assert auth_manager._session_info.is_authenticated is False
        assert auth_manager._session_info.username == ""


# ---- CSRF token extraction ----

class TestCsrfExtraction:
    def test_input_field(self, auth_manager):
        html = '<input type="hidden" name="_xfToken" value="abc123token">'
        token = auth_manager._extract_csrf_token(html)
        assert token == "abc123token"

    def test_js_variable(self, auth_manager):
        html = 'var config = { _xfToken: "js_token_456" };'
        token = auth_manager._extract_csrf_token(html)
        assert token == "js_token_456"

    def test_data_attribute(self, auth_manager):
        html = '<div data-csrf="csrf_data_789"></div>'
        token = auth_manager._extract_csrf_token(html)
        assert token == "csrf_data_789"

    def test_no_token(self, auth_manager):
        html = "<html><body>No token here</body></html>"
        token = auth_manager._extract_csrf_token(html)
        assert token is None


# ---- User info extraction ----

class TestUserInfoExtraction:
    def test_data_attributes(self, auth_manager):
        html = '<span data-user-id="12345" data-username="TestUser">TestUser</span>'
        username, user_id, avatar = auth_manager._extract_user_info(html)
        assert username == "TestUser"
        assert user_id == 12345

    def test_username_class(self, auth_manager):
        html = '<a class="username" href="/member/123">SomeUser</a>'
        username, user_id, avatar = auth_manager._extract_user_info(html)
        assert username == "SomeUser"

    def test_avatar_extraction(self, auth_manager):
        html = '<span class="avatar"><img src="/data/avatars/l/0/123.jpg" /></span>'
        username, user_id, avatar = auth_manager._extract_user_info(html)
        assert avatar == f"{F95_BASE}/data/avatars/l/0/123.jpg"

    def test_no_user_info(self, auth_manager):
        html = "<html><body>Guest view</body></html>"
        username, user_id, avatar = auth_manager._extract_user_info(html)
        assert username == ""
        assert user_id == 0
        assert avatar == ""


# ---- Cookie parsing ----

class TestCookieParsing:
    def test_basic_cookie(self, auth_manager):
        auth_manager._parse_set_cookie("xf_user=abc123; path=/; secure")
        cookies = list(auth_manager._cookies)
        assert len(cookies) == 1
        assert cookies[0].name == "xf_user"
        assert cookies[0].value == "abc123"

    def test_domain_cookie(self, auth_manager):
        auth_manager._parse_set_cookie("session=xyz; domain=.f95zone.to; path=/")
        cookies = list(auth_manager._cookies)
        assert len(cookies) == 1
        assert cookies[0].domain == ".f95zone.to"

    def test_invalid_cookie_no_crash(self, auth_manager):
        # Should not raise
        auth_manager._parse_set_cookie("")
        auth_manager._parse_set_cookie("no-equals-sign")
        assert True  # No exception


# ---- Session state ----

class TestSessionState:
    def test_is_authenticated_false_by_default(self, auth_manager):
        assert auth_manager.is_authenticated() is False

    def test_get_session_info(self, auth_manager):
        info = auth_manager.get_session_info()
        assert isinstance(info, SessionInfo)
        assert info.is_authenticated is False

    def test_logout_clears_session(self, auth_manager):
        auth_manager._session_info.is_authenticated = True
        auth_manager._session_info.username = "user"
        result = auth_manager.logout()
        assert result is True
        assert auth_manager.is_authenticated() is False
        assert auth_manager._session_info.username == ""


# ---- Rate limiting ----

class TestRateLimiting:
    def test_rate_limit_enforced(self, auth_manager):
        import time
        auth_manager._request_delay = 0.05  # 50ms for test speed
        auth_manager._last_request_time = time.time()
        start = time.time()
        auth_manager._rate_limit()
        elapsed = time.time() - start
        # Should have waited at least some time
        assert elapsed >= 0.01


# ---- Auto login ----

class TestAutoLogin:
    def test_no_credentials(self, auth_manager):
        result = auth_manager.auto_login()
        assert result.success is False
        assert result.error_code == "no_credentials"


# ---- AuthResult dataclass ----

class TestAuthResult:
    def test_success_result(self):
        r = AuthResult(success=True, message="OK", username="user")
        assert r.success is True
        assert r.username == "user"

    def test_failure_result(self):
        r = AuthResult(success=False, message="Wrong password", error_code="wrong_password")
        assert r.success is False
        assert r.error_code == "wrong_password"

    def test_2fa_result(self):
        r = AuthResult(success=False, requires_2fa=True)
        assert r.requires_2fa is True


# ---- StoredCredentials dataclass ----

class TestStoredCredentials:
    def test_defaults(self):
        creds = StoredCredentials()
        assert creds.username == ""
        assert creds.password_hash == ""
        assert creds.remember is False


# ---- SessionInfo dataclass ----

class TestSessionInfo:
    def test_defaults(self):
        info = SessionInfo()
        assert info.is_authenticated is False
        assert info.username == ""
        assert info.user_id == 0
        assert info.avatar_url == ""
        assert info.session_start is None
