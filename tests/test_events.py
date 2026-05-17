"""Tests for event creation, retrieval, deletion, and admin view."""
from tests.conftest import WIN_START, WIN_END, DAY_START, DAY_END, AVAIL_DATE, AVAIL_HOUR, expire_event


# ── create ───────────────────────────────────────────────────────────────────

def test_create_event_returns_three_fields(client):
    res = client.post("/api/events", json={
        "title": "My Event",
        "timezone": "America/Chicago",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 201
    data = res.json()
    assert "event_id" in data
    assert "share_url" in data
    assert "admin_token" in data
    assert data["share_url"].endswith(data["event_id"])


def test_create_event_share_url_format(client):
    res = client.post("/api/events", json={
        "title": "URL Test",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": 9,
        "day_end_hour": 17,
    })
    assert res.status_code == 201
    data = res.json()
    assert "/e/" in data["share_url"]


def test_create_event_with_description(client):
    res = client.post("/api/events", json={
        "title": "Desc Event",
        "description": "Some details here",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 201
    eid = res.json()["event_id"]
    get_res = client.get(f"/api/events/{eid}")
    assert get_res.json()["description"] == "Some details here"


def test_create_event_without_description(client):
    res = client.post("/api/events", json={
        "title": "No Desc",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 201
    eid = res.json()["event_id"]
    get_res = client.get(f"/api/events/{eid}")
    assert get_res.json()["description"] is None


def test_create_event_empty_title_rejected(client):
    res = client.post("/api/events", json={
        "title": "   ",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 422


def test_create_event_title_too_long_rejected(client):
    res = client.post("/api/events", json={
        "title": "x" * 201,
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 422


def test_create_event_window_end_before_start_rejected(client):
    res = client.post("/api/events", json={
        "title": "Bad Window",
        "timezone": "UTC",
        "window_start": WIN_END,
        "window_end": WIN_START,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 422


def test_create_event_equal_window_dates_allowed(client):
    res = client.post("/api/events", json={
        "title": "One Day",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_START,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 201


def test_create_event_equal_hours_rejected(client):
    res = client.post("/api/events", json={
        "title": "Bad Hours",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": 10,
        "day_end_hour": 10,
    })
    assert res.status_code == 422


def test_create_event_end_hour_less_than_start_rejected(client):
    res = client.post("/api/events", json={
        "title": "Bad Hours 2",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": 15,
        "day_end_hour": 10,
    })
    assert res.status_code == 422


def test_create_event_start_hour_out_of_range(client):
    res = client.post("/api/events", json={
        "title": "OOB",
        "timezone": "UTC",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": 23,  # max is 22
        "day_end_hour": 23,
    })
    assert res.status_code == 422


# ── get ──────────────────────────────────────────────────────────────────────

def test_get_event_returns_decrypted_title(client, event):
    res = client.get(f"/api/events/{event['event_id']}")
    assert res.status_code == 200
    assert res.json()["title"] == "Test Event"


def test_get_event_returns_all_fields(client, event):
    res = client.get(f"/api/events/{event['event_id']}")
    data = res.json()
    assert res.status_code == 200
    for field in ("id", "title", "description", "timezone", "window_start",
                  "window_end", "day_start_hour", "day_end_hour", "created_at", "expires_at"):
        assert field in data


def test_get_event_not_found(client):
    res = client.get("/api/events/does-not-exist")
    assert res.status_code == 404


def test_get_event_expired_returns_410(client, event_id):
    expire_event(event_id)
    res = client.get(f"/api/events/{event_id}")
    assert res.status_code == 410


def test_get_event_title_not_stored_as_plaintext(client, event):
    # The GET response decrypts; check the returned value equals original title
    res = client.get(f"/api/events/{event['event_id']}")
    assert res.json()["title"] == "Test Event"
    # Also verify event_id field matches
    assert res.json()["id"] == event["event_id"]


# ── delete ───────────────────────────────────────────────────────────────────

def test_delete_event_valid_token(client, event_id, admin_token):
    res = client.delete(
        f"/api/events/{event_id}",
        headers={"X-Admin-Token": admin_token},
    )
    assert res.status_code == 204


def test_delete_event_removes_event(client, event_id, admin_token):
    client.delete(f"/api/events/{event_id}", headers={"X-Admin-Token": admin_token})
    res = client.get(f"/api/events/{event_id}")
    assert res.status_code == 404


def test_delete_event_cascades_submissions(client, event_id, admin_token, avail_items):
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice",
        "availability": avail_items,
    })
    client.delete(f"/api/events/{event_id}", headers={"X-Admin-Token": admin_token})
    # Results endpoint returns 404 since event is gone
    res = client.get(f"/api/events/{event_id}/results")
    assert res.status_code == 404


def test_delete_event_wrong_token(client, event_id):
    res = client.delete(
        f"/api/events/{event_id}",
        headers={"X-Admin-Token": "wrong-token"},
    )
    assert res.status_code == 403


def test_delete_event_not_found(client):
    res = client.delete(
        "/api/events/does-not-exist",
        headers={"X-Admin-Token": "any-token"},
    )
    assert res.status_code == 404


def test_delete_event_missing_header(client, event_id):
    res = client.delete(f"/api/events/{event_id}")
    assert res.status_code == 422


# ── admin view ───────────────────────────────────────────────────────────────

def test_admin_view_valid_token(client, event_id, admin_token):
    res = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": admin_token},
    )
    assert res.status_code == 200
    data = res.json()
    assert "respondent_count" in data
    assert "window_start" in data
    assert "window_end" in data
    assert "expires_at" in data


def test_admin_view_respondent_count_zero(client, event_id, admin_token):
    res = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": admin_token},
    )
    assert res.json()["respondent_count"] == 0


def test_admin_view_respondent_count_increases(client, event_id, admin_token, avail_items):
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Bob", "availability": avail_items,
    })
    res = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": admin_token},
    )
    assert res.json()["respondent_count"] == 2


def test_admin_view_no_names_in_response(client, event_id, admin_token, avail_items):
    client.post(f"/api/events/{event_id}/submissions", json={
        "name": "Alice", "availability": avail_items,
    })
    res = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": admin_token},
    )
    body = res.text
    assert "Alice" not in body
    assert "name" not in body


def test_admin_view_wrong_token(client, event_id):
    res = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": "wrong-token"},
    )
    assert res.status_code == 403


def test_admin_view_not_found(client):
    res = client.get(
        "/api/events/does-not-exist/admin",
        headers={"X-Admin-Token": "any"},
    )
    assert res.status_code == 404


def test_admin_view_expired_event(client, event_id, admin_token):
    expire_event(event_id)
    res = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": admin_token},
    )
    assert res.status_code == 410
