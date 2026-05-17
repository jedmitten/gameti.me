"""Tests for site-admin username transfer endpoint."""
from tests.conftest import SITE_ADMIN_SECRET, get_account_id_by_session


_ENDPOINT = "/api/site-admin/transfer-username"


def _transfer(client, username, new_passphrase, secret=SITE_ADMIN_SECRET):
    return client.post(_ENDPOINT, json={
        "username": username,
        "new_passphrase": new_passphrase,
    }, headers={"X-Site-Admin-Secret": secret})


def test_transfer_username_success(client, account):
    res = _transfer(client, "testuser", "brandnewpassword123")
    assert res.status_code == 200
    assert "transferred" in res.json()["message"].lower()


def test_transfer_username_wrong_secret(client, account):
    res = _transfer(client, "testuser", "brandnewpassword123", secret="wrongsecret")
    assert res.status_code == 403


def test_transfer_username_missing_header(client, account):
    res = client.post(_ENDPOINT, json={
        "username": "testuser", "new_passphrase": "brandnewpassword123",
    })
    assert res.status_code == 422


def test_transfer_username_not_found(client):
    res = _transfer(client, "nobody", "brandnewpassword123")
    assert res.status_code == 404


def test_transfer_invalidates_existing_sessions(client, account):
    old_session = account["session_token"]
    _transfer(client, "testuser", "brandnewpassword123")
    res = client.get("/api/accounts/me", headers={"X-Session-Token": old_session})
    assert res.status_code == 401


def test_transfer_old_passphrase_fails_login(client, account):
    _transfer(client, "testuser", "brandnewpassword123")
    res = client.post("/api/accounts/session", json={
        "username": "testuser",
        "passphrase": "securepassword123",  # original passphrase
    })
    assert res.status_code == 401


def test_transfer_new_passphrase_works_login(client, account):
    _transfer(client, "testuser", "brandnewpassword123")
    res = client.post("/api/accounts/session", json={
        "username": "testuser",
        "passphrase": "brandnewpassword123",
    })
    assert res.status_code == 200
    assert "session_token" in res.json()


def test_transfer_username_case_insensitive(client, account):
    # "TESTUSER" should resolve to the same account as "testuser"
    res = _transfer(client, "TESTUSER", "brandnewpassword123")
    assert res.status_code == 200
