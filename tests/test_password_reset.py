"""Tests for password reset functionality, timezone parsing, email building, and routes."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from auth.restore import (
    build_email_content,
    build_reset_url,
    generate_token,
    is_expired,
    parse_token_date,
    send_email_direct,
)


def test_generate_token():
    token = generate_token()
    assert isinstance(token, str)
    assert len(token) >= 32


def test_parse_token_date_formats():
    # 1. Datetime object (naive & aware)
    now_naive = datetime.now()
    parsed_naive = parse_token_date(now_naive)
    assert parsed_naive.tzinfo == timezone.utc

    now_aware = datetime.now(timezone.utc)
    assert parse_token_date(now_aware) == now_aware

    # 2. ISO format with 'Z'
    dt_z = "2026-08-27T10:00:00Z"
    parsed_z = parse_token_date(dt_z)
    assert parsed_z is not None
    assert parsed_z.year == 2026
    assert parsed_z.tzinfo == timezone.utc

    # 3. ISO format with offset
    dt_offset = "2026-08-27T10:00:00+00:00"
    parsed_offset = parse_token_date(dt_offset)
    assert parsed_offset is not None
    assert parsed_offset.year == 2026

    # 4. Standard SQL string
    dt_sql = "2026-08-27 10:00:00"
    parsed_sql = parse_token_date(dt_sql)
    assert parsed_sql is not None
    assert parsed_sql.year == 2026
    assert parsed_sql.tzinfo == timezone.utc

    # 5. Invalid / None
    assert parse_token_date(None) is None
    assert parse_token_date("") is None
    assert parse_token_date("not-a-date") is None


def test_is_expired():
    now_utc = datetime.now(timezone.utc)

    # Fresh token created 1 hour ago
    fresh_date = now_utc - timedelta(hours=1)
    assert is_expired(fresh_date, max_age_hours=24) is False

    # Expired token created 25 hours ago
    expired_date = now_utc - timedelta(hours=25)
    assert is_expired(expired_date, max_age_hours=24) is True

    # Expired ISO string with offset
    expired_str = (now_utc - timedelta(hours=26)).isoformat()
    assert is_expired(expired_str, max_age_hours=24) is True

    # Fresh ISO string with 'Z'
    fresh_str = (now_utc - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert is_expired(fresh_str, max_age_hours=24) is False


def test_build_reset_url(app_module):
    app = app_module.app
    with app.test_request_context():
        # When RENDER_EXTERNAL_URL is set in config
        app.config["RENDER_EXTERNAL_URL"] = "https://kineto-app.onrender.com"
        url = build_reset_url("test-token-123")
        assert url == "https://kineto-app.onrender.com/passwordreset/test-token-123"

        # When BASE_URL is set and RENDER_EXTERNAL_URL is cleared
        app.config["RENDER_EXTERNAL_URL"] = None
        app.config["BASE_URL"] = "https://mycustomdomain.com"
        url = build_reset_url("test-token-123")
        assert url == "https://mycustomdomain.com/passwordreset/test-token-123"

        # Fallback to Flask request host
        app.config["BASE_URL"] = None
        url = build_reset_url("test-token-123")
        assert "/passwordreset/test-token-123" in url


def test_build_email_content():
    reset_url = "https://example.com/passwordreset/sample-token"
    plain, html = build_email_content(reset_url)

    assert "Kineto - Password Reset" in plain
    assert reset_url in plain
    assert "24 hours" in plain

    assert "<!DOCTYPE html>" in html
    assert reset_url in html
    assert "Reset Password" in html
    assert "KINETO" in html


def test_password_reset_page_get(client):
    res = client.get("/passwordreset")
    assert res.status_code == 200
    assert b"Reset Password" in res.data
    assert b"Send Reset Link" in res.data


def test_password_reset_post_empty_email(client):
    res = client.post("/passwordreset", data={"email": ""}, follow_redirects=True)
    assert res.status_code == 200
    assert b"Please enter a valid email address." in res.data


def test_password_reset_post_valid_email(client, monkeypatch):
    import auth.restore as restore_module

    fake_user = {"id": 42, "email": "test@example.com", "username": "cinephile"}
    monkeypatch.setattr(restore_module, "get_user_by_email", lambda email: fake_user)
    monkeypatch.setattr(restore_module, "delete_user_tokens", lambda uid: None)
    monkeypatch.setattr(restore_module, "insert_token", lambda uid, tok, dt: None)

    # Mock Thread so we don't start background work during unit test
    mock_thread = MagicMock()
    monkeypatch.setattr(restore_module, "Thread", mock_thread)

    res = client.post("/passwordreset", data={"email": "test@example.com"}, follow_redirects=True)
    assert res.status_code == 200
    assert b"If an account exists with this email" in res.data


def test_password_reset_post_json(client, monkeypatch):
    import auth.restore as restore_module

    fake_user = {"id": 42, "email": "test@example.com", "username": "cinephile"}
    monkeypatch.setattr(restore_module, "get_user_by_email", lambda email: fake_user)
    monkeypatch.setattr(restore_module, "delete_user_tokens", lambda uid: None)
    monkeypatch.setattr(restore_module, "insert_token", lambda uid, tok, dt: None)
    monkeypatch.setattr(restore_module, "Thread", MagicMock())

    res = client.post("/passwordreset", json={"email": "test@example.com"})
    assert res.status_code == 200
    data = res.get_json()
    assert "If an account exists with this email" in data["message"]


def test_reset_token_page_invalid_token(client, monkeypatch):
    import auth.restore as restore_module

    monkeypatch.setattr(restore_module, "get_token", lambda tok: None)

    res = client.get("/passwordreset/invalid-tok", follow_redirects=True)
    assert res.status_code == 200
    assert b"The password reset link is invalid or has already been used." in res.data


def test_reset_token_page_expired_token(client, monkeypatch):
    import auth.restore as restore_module

    old_date = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    monkeypatch.setattr(restore_module, "get_token", lambda tok: {"token": tok, "user_id": 1, "created_at": old_date})
    monkeypatch.setattr(restore_module, "delete_token", lambda tok: None)

    res = client.get("/passwordreset/expired-tok", follow_redirects=True)
    assert res.status_code == 200
    assert b"The password reset link has expired" in res.data


def test_reset_token_page_valid_token_get(client, monkeypatch):
    import auth.restore as restore_module

    fresh_date = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    monkeypatch.setattr(restore_module, "get_token", lambda tok: {"token": tok, "user_id": 1, "created_at": fresh_date})

    res = client.get("/passwordreset/valid-tok")
    assert res.status_code == 200
    assert b"Set New Password" in res.data
    assert b"Confirm New Password" in res.data


def test_reset_password_post_mismatched(client, monkeypatch):
    import auth.restore as restore_module

    fresh_date = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    monkeypatch.setattr(restore_module, "get_token", lambda tok: {"token": tok, "user_id": 1, "created_at": fresh_date})

    res = client.post(
        "/passwordreset/valid-tok",
        data={"password": "newpassword123", "confirm_password": "differentpassword"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Passwords do not match." in res.data


def test_reset_password_post_success(client, monkeypatch):
    import auth.restore as restore_module

    fresh_date = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    monkeypatch.setattr(restore_module, "get_token", lambda tok: {"token": tok, "user_id": 10, "created_at": fresh_date})

    updated_users = []
    deleted_tokens = []
    monkeypatch.setattr(restore_module, "update_user_password", lambda uid, pwd: updated_users.append((uid, pwd)))
    monkeypatch.setattr(restore_module, "delete_token", lambda tok: deleted_tokens.append(tok))

    res = client.post(
        "/passwordreset/valid-tok",
        data={"password": "supersecretpassword", "confirm_password": "supersecretpassword"},
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Password has been reset successfully!" in res.data
    assert len(updated_users) == 1
    assert updated_users[0][0] == 10
    assert len(deleted_tokens) == 1
    assert deleted_tokens[0] == "valid-tok"
