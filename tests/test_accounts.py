"""Tests for account registration, authentication, and recovery."""
import asyncio
from datetime import datetime, timedelta, timezone

from tests.conftest import (
    get_account_id_by_session, set_recovery_token, run,
    WIN_START, WIN_END, DAY_START, DAY_END, AVAIL_DATE, AVAIL_HOUR,
)
from backend.database import get_db
from backend.crypto import hash_token


# ── check-username ────────────────────────────────────────────────────────────

def test_check_username_available(client):
    res = client.post("/api/accounts/check-username", json={"username": "newuser"})
    assert res.status_code == 200
    assert res.json()["available"] is True


def test_check_username_taken_after_register(client):
    client.post("/api/accounts", json={
        "username": "taken", "email": "t@t.com", "passphrase": "password123",
    })
    res = client.post("/api/accounts/check-username", json={"username": "taken"})
    assert res.json()["available"] is False


def test_check_username_case_insensitive(client):
    client.post("/api/accounts", json={
        "username": "MyUser", "email": "m@m.com", "passphrase": "password123",
    })
    res = client.post("/api/accounts/check-username", json={"username": "myuser"})
    assert res.json()["available"] is False


# ── register ──────────────────────────────────────────────────────────────────

def test_register_success(client):
    res = client.post("/api/accounts", json={
        "username": "alice",
        "email": "alice@example.com",
        "passphrase": "securepassword",
    })
    assert res.status_code == 201
    data = res.json()
    assert "session_token" in data
    assert data["username"] == "alice"


def test_register_returns_session_token(client):
    res = client.post("/api/accounts", json={
        "username": "bob", "email": "b@b.com", "passphrase": "securepassword",
    })
    token = res.json()["session_token"]
    assert token is not None and len(token) > 20


def test_register_username_taken_returns_409(client):
    client.post("/api/accounts", json={
        "username": "carol", "email": "c@c.com", "passphrase": "securepassword",
    })
    res = client.post("/api/accounts", json={
        "username": "carol", "email": "other@c.com", "passphrase": "securepassword",
    })
    assert res.status_code == 409


def test_register_username_too_short(client):
    res = client.post("/api/accounts", json={
        "username": "ab", "email": "ab@ab.com", "passphrase": "securepassword",
    })
    assert res.status_code == 422


def test_register_username_invalid_chars(client):
    res = client.post("/api/accounts", json={
        "username": "bad user!", "email": "x@x.com", "passphrase": "securepassword",
    })
    assert res.status_code == 422


def test_register_username_too_long(client):
    res = client.post("/api/accounts", json={
        "username": "a" * 51, "email": "x@x.com", "passphrase": "securepassword",
    })
    assert res.status_code == 422


def test_register_weak_passphrase_rejected(client):
    res = client.post("/api/accounts", json={
        "username": "weakpass", "email": "w@w.com", "passphrase": "short",
    })
    assert res.status_code == 422


def test_register_allows_hyphens_underscores(client):
    res = client.post("/api/accounts", json={
        "username": "my-user_name", "email": "m@m.com", "passphrase": "securepassword",
    })
    assert res.status_code == 201


# ── login ─────────────────────────────────────────────────────────────────────

def test_login_success(client, account):
    res = client.post("/api/accounts/session", json={
        "username": "testuser",
        "passphrase": "securepassword123",
    })
    assert res.status_code == 200
    assert "session_token" in res.json()
    assert res.json()["username"] == "testuser"


def test_login_wrong_passphrase(client, account):
    res = client.post("/api/accounts/session", json={
        "username": "testuser",
        "passphrase": "wrongpassword",
    })
    assert res.status_code == 401


def test_login_unknown_username_same_401(client):
    res = client.post("/api/accounts/session", json={
        "username": "doesnotexist",
        "passphrase": "anypassword",
    })
    assert res.status_code == 401
    # Same detail message as wrong password (prevent enumeration)


def test_login_unknown_and_wrong_same_error_message(client, account):
    bad_user = client.post("/api/accounts/session", json={
        "username": "nobody", "passphrase": "abc",
    })
    bad_pass = client.post("/api/accounts/session", json={
        "username": "testuser", "passphrase": "abc",
    })
    assert bad_user.json()["detail"] == bad_pass.json()["detail"]


def test_login_username_case_insensitive(client, account):
    res = client.post("/api/accounts/session", json={
        "username": "TESTUSER",
        "passphrase": "securepassword123",
    })
    assert res.status_code == 200


# ── logout ────────────────────────────────────────────────────────────────────

def test_logout_invalidates_session(client, session_token):
    client.delete("/api/accounts/session", headers={"X-Session-Token": session_token})
    res = client.get("/api/accounts/me", headers={"X-Session-Token": session_token})
    assert res.status_code == 401


def test_logout_invalid_token_still_204(client):
    res = client.delete("/api/accounts/session", headers={"X-Session-Token": "garbage"})
    assert res.status_code == 204


# ── get me ────────────────────────────────────────────────────────────────────

def test_get_me_returns_username(client, session_token):
    res = client.get("/api/accounts/me", headers={"X-Session-Token": session_token})
    assert res.status_code == 200
    assert res.json()["username"] == "testuser"


def test_get_me_returns_has_email(client, session_token):
    res = client.get("/api/accounts/me", headers={"X-Session-Token": session_token})
    assert res.json()["has_email"] is True


def test_get_me_no_raw_email_in_response(client, session_token):
    res = client.get("/api/accounts/me", headers={"X-Session-Token": session_token})
    assert "test@example.com" not in res.text


def test_get_me_invalid_session(client):
    res = client.get("/api/accounts/me", headers={"X-Session-Token": "bad-token"})
    assert res.status_code == 401


def test_get_me_missing_header(client):
    res = client.get("/api/accounts/me")
    assert res.status_code == 422


# ── my events ─────────────────────────────────────────────────────────────────

def test_my_events_empty(client, session_token):
    res = client.get("/api/accounts/me/events", headers={"X-Session-Token": session_token})
    assert res.status_code == 200
    assert res.json() == []


def test_my_events_shows_participated_events(client, session_token, avail_items):
    # Create event and submit with session
    event = client.post("/api/events", json={
        "title": "Team Sync",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    }).json()

    client.post(
        f"/api/events/{event['event_id']}/submissions",
        json={"name": "testuser", "availability": avail_items},
        headers={"X-Session-Token": session_token},
    )

    res = client.get("/api/accounts/me/events", headers={"X-Session-Token": session_token})
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["title"] == "Team Sync"
    assert res.json()[0]["event_id"] == event["event_id"]


def test_my_events_does_not_show_ephemeral_events(client, session_token, event_id, avail_items):
    # Submit to event_id WITHOUT session token (ephemeral)
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "OtherName", "availability": avail_items,
    })
    res = client.get("/api/accounts/me/events", headers={"X-Session-Token": session_token})
    assert res.json() == []


# ── recovery ──────────────────────────────────────────────────────────────────

def test_recovery_request_always_returns_204(client, account):
    res = client.post("/api/accounts/recovery", json={
        "username": "testuser", "email": "test@example.com",
    })
    assert res.status_code == 204


def test_recovery_nonexistent_user_still_204(client):
    res = client.post("/api/accounts/recovery", json={
        "username": "nobody", "email": "nobody@example.com",
    })
    assert res.status_code == 204


def test_recovery_confirm_valid_token(client, account):
    # Manually plant a valid recovery token
    account_id = get_account_id_by_session(account["session_token"])
    raw_token = "validrecoverytoken12345678901234"
    token_hash = hash_token(raw_token)
    expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
    set_recovery_token(account_id, token_hash, expires)

    res = client.post("/api/accounts/recovery/confirm", json={
        "token": raw_token,
        "new_passphrase": "newstrongpassword",
    })
    assert res.status_code == 200
    assert "session_token" in res.json()
    assert res.json()["username"] == "testuser"


def test_recovery_confirm_creates_new_session(client, account):
    account_id = get_account_id_by_session(account["session_token"])
    raw_token = "recovertoken12345678901234567890"
    token_hash = hash_token(raw_token)
    expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
    set_recovery_token(account_id, token_hash, expires)

    res = client.post("/api/accounts/recovery/confirm", json={
        "token": raw_token, "new_passphrase": "newstrongpassword",
    })
    new_token = res.json()["session_token"]

    # New session works
    me = client.get("/api/accounts/me", headers={"X-Session-Token": new_token})
    assert me.status_code == 200


def test_recovery_confirm_old_sessions_invalidated(client, account):
    old_token = account["session_token"]
    account_id = get_account_id_by_session(old_token)
    raw_token = "recovertokeninvalidatesessions12"
    token_hash = hash_token(raw_token)
    expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
    set_recovery_token(account_id, token_hash, expires)

    client.post("/api/accounts/recovery/confirm", json={
        "token": raw_token, "new_passphrase": "newstrongpassword",
    })

    # Old session is now invalid
    res = client.get("/api/accounts/me", headers={"X-Session-Token": old_token})
    assert res.status_code == 401


def test_recovery_confirm_expired_token(client, account):
    account_id = get_account_id_by_session(account["session_token"])
    raw_token = "expiredrecoverytoken12345678901"
    token_hash = hash_token(raw_token)
    expires = (datetime.now(tz=timezone.utc) - timedelta(minutes=1)).isoformat()
    set_recovery_token(account_id, token_hash, expires)

    res = client.post("/api/accounts/recovery/confirm", json={
        "token": raw_token, "new_passphrase": "newstrongpassword",
    })
    assert res.status_code == 400


def test_recovery_confirm_invalid_token(client):
    res = client.post("/api/accounts/recovery/confirm", json={
        "token": "totallywrongtoken",
        "new_passphrase": "newstrongpassword",
    })
    assert res.status_code == 400


def test_recovery_confirm_weak_passphrase(client, account):
    account_id = get_account_id_by_session(account["session_token"])
    raw_token = "weakpassrecoverytoken1234567890"
    token_hash = hash_token(raw_token)
    expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
    set_recovery_token(account_id, token_hash, expires)

    res = client.post("/api/accounts/recovery/confirm", json={
        "token": raw_token, "new_passphrase": "short",
    })
    assert res.status_code == 422


def test_recovery_new_passphrase_works_for_login(client, account):
    account_id = get_account_id_by_session(account["session_token"])
    raw_token = "loginafterrecovery1234567890123"
    token_hash = hash_token(raw_token)
    expires = (datetime.now(tz=timezone.utc) + timedelta(minutes=10)).isoformat()
    set_recovery_token(account_id, token_hash, expires)

    client.post("/api/accounts/recovery/confirm", json={
        "token": raw_token, "new_passphrase": "brandnewpassword",
    })

    login = client.post("/api/accounts/session", json={
        "username": "testuser", "passphrase": "brandnewpassword",
    })
    assert login.status_code == 200
