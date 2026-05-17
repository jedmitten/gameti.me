"""Tests for submission creation, updates, and retrieval."""
from datetime import date, timedelta
from tests.conftest import (
    WIN_START, WIN_END, AVAIL_DATE, AVAIL_HOUR, DAY_START, DAY_END,
    expire_event,
)

_OUTSIDE_DATE = (date.today() + timedelta(days=90)).isoformat()
_OUTSIDE_EARLY_DATE = (date.today() - timedelta(days=1)).isoformat()


# ── create (ephemeral) ────────────────────────────────────────────────────────

def test_submit_ephemeral_returns_201(client, event_id, avail_items):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    assert res.status_code == 201


def test_submit_ephemeral_returns_edit_token(client, event_id, avail_items):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    data = res.json()
    assert "edit_token" in data
    assert data["edit_token"] is not None
    assert len(data["edit_token"]) > 20


def test_submit_ephemeral_returns_submission_id(client, event_id, avail_items):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    assert res.json()["submission_id"] is not None


# ── create (account-based) ────────────────────────────────────────────────────

def test_submit_with_session_returns_null_edit_token(client, event_id, session_token, avail_items):
    res = client.post(
        f"/api/events/{event_id}/submissions",
        json={"name": "testuser", "availability": avail_items},
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code == 201
    assert res.json()["edit_token"] is None


# ── create (inline registration) ─────────────────────────────────────────────

def test_submit_inline_register_creates_account(client, event_id, avail_items):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "newuser",
        "availability": avail_items,
        "register": True,
        "email": "new@example.com",
        "passphrase": "strongpassword1",
    })
    assert res.status_code == 201
    # Name is now registered
    chk = client.post("/api/accounts/check-username", json={"username": "newuser"})
    assert chk.json()["available"] is False


def test_submit_inline_register_null_edit_token(client, event_id, avail_items):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "reguser",
        "availability": avail_items,
        "register": True,
        "email": "reg@example.com",
        "passphrase": "strongpassword1",
    })
    assert res.status_code == 201
    assert res.json()["edit_token"] is None


def test_submit_inline_register_weak_passphrase_rejected(client, event_id, avail_items):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "weakuser",
        "availability": avail_items,
        "register": True,
        "email": "weak@example.com",
        "passphrase": "short",
    })
    assert res.status_code == 422


# ── registered-name guard ─────────────────────────────────────────────────────

def test_submit_registered_name_as_ephemeral_returns_409(client, event_id, account, avail_items):
    # account fixture registers "testuser"
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "testuser",
        "availability": avail_items,
    })
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail.get("registered") is True


def test_submit_registered_name_case_insensitive_guard(client, event_id, account, avail_items):
    # "TESTUSER" should be blocked the same as "testuser"
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "TESTUSER",
        "availability": avail_items,
    })
    assert res.status_code == 409


def test_submit_registered_name_with_valid_session_allowed(client, event_id, session_token, avail_items):
    res = client.post(
        f"/api/events/{event_id}/submissions",
        json={"name": "testuser", "availability": avail_items},
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code == 201


# ── name collision within event ───────────────────────────────────────────────

def test_same_ephemeral_name_in_event_rejected(client, event_id, avail_items):
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    assert res.status_code == 409
    assert "taken" in res.json()["detail"].lower()


def test_same_name_different_events_allowed(client, avail_items):
    def make_event():
        r = client.post("/api/events", json={
            "title": "Evt", "timezone": "UTC",
            "window_start": WIN_START, "window_end": WIN_END,
            "day_start_hour": DAY_START, "day_end_hour": DAY_END,
        })
        return r.json()["event_id"]

    eid1 = make_event()
    eid2 = make_event()

    r1 = client.post(f"/api/events/{eid1}/submissions", json={
        "name": "SharedName", "availability": avail_items,
    })
    r2 = client.post(f"/api/events/{eid2}/submissions", json={
        "name": "SharedName", "availability": avail_items,
    })
    assert r1.status_code == 201
    assert r2.status_code == 201


# ── availability validation ───────────────────────────────────────────────────

def test_submit_date_outside_window_rejected(client, event_id):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice",
        "availability": [{"date": _OUTSIDE_DATE, "hour": AVAIL_HOUR, "status": "yes"}],
    })
    assert res.status_code == 422


def test_submit_date_before_window_rejected(client, event_id):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice",
        "availability": [{"date": _OUTSIDE_EARLY_DATE, "hour": AVAIL_HOUR, "status": "yes"}],
    })
    assert res.status_code == 422


def test_submit_hour_below_day_start_rejected(client, event_id):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice",
        "availability": [{"date": AVAIL_DATE, "hour": DAY_START - 1, "status": "yes"}],
    })
    assert res.status_code == 422


def test_submit_hour_at_or_above_day_end_rejected(client, event_id):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice",
        "availability": [{"date": AVAIL_DATE, "hour": DAY_END, "status": "yes"}],
    })
    assert res.status_code == 422


def test_submit_invalid_status_rejected(client, event_id):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice",
        "availability": [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "meh"}],
    })
    assert res.status_code == 422


def test_submit_empty_availability_allowed(client, event_id):
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": [],
    })
    assert res.status_code == 201


def test_submit_all_three_statuses(client, event_id):
    items = [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"},
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR + 1, "status": "maybe"},
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR + 2, "status": "no"},
    ]
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": items,
    })
    assert res.status_code == 201


def test_submit_event_not_found(client, avail_items):
    res = client.post("/api/events/does-not-exist/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    assert res.status_code == 404


def test_submit_expired_event_rejected(client, event_id, avail_items):
    expire_event(event_id)
    res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    assert res.status_code == 410


# ── update ────────────────────────────────────────────────────────────────────

def test_update_with_edit_token(client, event_id, avail_items):
    sub = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    }).json()
    edit_token = sub["edit_token"]

    new_items = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR + 1, "status": "maybe"}]
    res = client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": new_items},
        headers={"X-Edit-Token": edit_token},
    )
    assert res.status_code == 200


def test_update_replaces_availability(client, event_id, avail_items):
    sub = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    }).json()
    edit_token = sub["edit_token"]

    new_items = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR + 1, "status": "no"}]
    client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": new_items},
        headers={"X-Edit-Token": edit_token},
    )

    me = client.get(
        f"/api/events/{event_id}/submissions/me",
        headers={"X-Edit-Token": edit_token},
    ).json()
    assert len(me["availability"]) == 1
    assert me["availability"][0]["hour"] == AVAIL_HOUR + 1
    assert me["availability"][0]["status"] == "no"


def test_update_with_session_token(client, event_id, session_token, avail_items):
    client.post(
        f"/api/events/{event_id}/submissions",
        json={"name": "testuser", "availability": avail_items},
        headers={"X-Session-Token": session_token},
    )
    new_items = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "maybe"}]
    res = client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": new_items},
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code == 200


def test_update_wrong_edit_token(client, event_id, avail_items):
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    res = client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": avail_items},
        headers={"X-Edit-Token": "wrong-token"},
    )
    assert res.status_code == 401


def test_update_no_auth_rejected(client, event_id, avail_items):
    res = client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": avail_items},
    )
    assert res.status_code == 401


def test_update_no_submission_for_session(client, event_id, session_token, avail_items):
    res = client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": avail_items},
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code == 404


# ── get own submission ────────────────────────────────────────────────────────

def test_get_my_submission_by_edit_token(client, event_id, avail_items):
    sub = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    }).json()

    res = client.get(
        f"/api/events/{event_id}/submissions/me",
        headers={"X-Edit-Token": sub["edit_token"]},
    )
    assert res.status_code == 200
    assert len(res.json()["availability"]) == 1
    assert res.json()["availability"][0]["status"] == "yes"


def test_get_my_submission_by_session(client, event_id, session_token, avail_items):
    client.post(
        f"/api/events/{event_id}/submissions",
        json={"name": "testuser", "availability": avail_items},
        headers={"X-Session-Token": session_token},
    )
    res = client.get(
        f"/api/events/{event_id}/submissions/me",
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code == 200
    assert len(res.json()["availability"]) == 1


def test_get_my_submission_bad_edit_token(client, event_id):
    res = client.get(
        f"/api/events/{event_id}/submissions/me",
        headers={"X-Edit-Token": "bad-token"},
    )
    assert res.status_code == 401


def test_get_my_submission_no_auth(client, event_id):
    res = client.get(f"/api/events/{event_id}/submissions/me")
    assert res.status_code == 401


def test_get_my_submission_no_submission_for_session(client, event_id, session_token):
    res = client.get(
        f"/api/events/{event_id}/submissions/me",
        headers={"X-Session-Token": session_token},
    )
    assert res.status_code == 404
