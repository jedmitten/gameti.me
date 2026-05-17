"""End-to-end integration tests covering full user flows."""
from datetime import date, timedelta
from tests.conftest import (
    WIN_START, WIN_END, DAY_START, DAY_END, AVAIL_DATE, AVAIL_HOUR,
    SITE_ADMIN_SECRET,
)


def _make_event(client, title="Integration Event"):
    r = client.post("/api/events", json={
        "title": title,
        "timezone": "America/Chicago",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    return r.json()


def _register(client, username, email="u@u.com", passphrase="strongpassword1"):
    r = client.post("/api/accounts", json={
        "username": username, "email": email, "passphrase": passphrase,
    })
    return r.json()


# ── full ephemeral flow ───────────────────────────────────────────────────────

def test_full_ephemeral_flow(client):
    # 1. Create event
    event = _make_event(client, "Ephemeral Flow Event")
    event_id = event["event_id"]
    admin_token = event["admin_token"]

    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    # 2. Submit availability (ephemeral)
    sub_res = client.post(f"/api/events/{event_id}/submissions", json={
        "name": "EphUser", "availability": avail,
    })
    assert sub_res.status_code == 201
    edit_token = sub_res.json()["edit_token"]
    assert edit_token is not None

    # 3. View results — one respondent
    results = client.get(f"/api/events/{event_id}/results").json()
    assert results["respondent_count"] == 1
    assert results["slots"][0]["yes"] == 1

    # 4. Edit submission — change to "maybe"
    updated = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "maybe"}]
    edit_res = client.put(
        f"/api/events/{event_id}/submissions",
        json={"availability": updated},
        headers={"X-Edit-Token": edit_token},
    )
    assert edit_res.status_code == 200

    # 5. Results updated — now 1 maybe, 0 yes
    results2 = client.get(f"/api/events/{event_id}/results").json()
    slot = results2["slots"][0]
    assert slot["yes"] == 0
    assert slot["maybe"] == 1

    # 6. Admin sees count, not names
    admin = client.get(
        f"/api/events/{event_id}/admin",
        headers={"X-Admin-Token": admin_token},
    ).json()
    assert admin["respondent_count"] == 1
    assert "EphUser" not in str(admin)


def test_full_account_flow(client):
    # 1. Register
    acct = _register(client, "flowuser")
    session = acct["session_token"]

    # 2. Create event
    event = _make_event(client, "Account Flow Event")
    event_id = event["event_id"]

    # 3. Submit with session (account-based)
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]
    sub = client.post(
        f"/api/events/{event_id}/submissions",
        json={"name": "flowuser", "availability": avail},
        headers={"X-Session-Token": session},
    ).json()
    assert sub["edit_token"] is None  # account-based: no edit token

    # 4. My events shows the participated event
    my_events = client.get(
        "/api/accounts/me/events",
        headers={"X-Session-Token": session},
    ).json()
    assert len(my_events) == 1
    assert my_events[0]["event_id"] == event_id
    assert my_events[0]["title"] == "Account Flow Event"

    # 5. Get own submission via session
    me_sub = client.get(
        f"/api/events/{event_id}/submissions/me",
        headers={"X-Session-Token": session},
    ).json()
    assert me_sub["availability"][0]["status"] == "yes"


# ── name reservation enforcement ─────────────────────────────────────────────

def test_name_reservation_blocks_ephemeral(client):
    _register(client, "reserved")
    event = _make_event(client)
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    # Try to submit as ephemeral with the registered name
    res = client.post(f"/api/events/{event['event_id']}/submissions", json={
        "name": "reserved", "availability": avail,
    })
    assert res.status_code == 409
    assert res.json()["detail"]["registered"] is True


def test_name_reservation_case_insensitive(client):
    _register(client, "MyName")
    event = _make_event(client)
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    for variant in ("myname", "MYNAME", "MyName", "mYnAmE"):
        res = client.post(f"/api/events/{event['event_id']}/submissions", json={
            "name": variant, "availability": avail,
        })
        assert res.status_code == 409, f"Expected 409 for variant '{variant}'"


def test_sign_in_allows_reserved_name(client):
    acct = _register(client, "SignInUser")
    session = acct["session_token"]
    event = _make_event(client)
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    res = client.post(
        f"/api/events/{event['event_id']}/submissions",
        json={"name": "SignInUser", "availability": avail},
        headers={"X-Session-Token": session},
    )
    assert res.status_code == 201


# ── multi-respondent overlap ──────────────────────────────────────────────────

def test_multi_respondent_overlap_aggregation(client):
    event = _make_event(client)
    eid = event["event_id"]
    date2 = (date.fromisoformat(AVAIL_DATE) + timedelta(days=1)).isoformat()

    # Alice: yes on both slots
    client.post(f"/api/events/{eid}/submissions", json={
        "name": "Alice", "availability": [
            {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"},
            {"date": date2,      "hour": AVAIL_HOUR, "status": "yes"},
        ],
    })
    # Bob: yes on slot 1, no on slot 2
    client.post(f"/api/events/{eid}/submissions", json={
        "name": "Bob", "availability": [
            {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"},
            {"date": date2,      "hour": AVAIL_HOUR, "status": "no"},
        ],
    })
    # Carol: maybe on slot 1 only
    client.post(f"/api/events/{eid}/submissions", json={
        "name": "Carol", "availability": [
            {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "maybe"},
        ],
    })

    data = client.get(f"/api/events/{eid}/results").json()
    assert data["respondent_count"] == 3

    by_slot = {(s["date"], s["hour"]): s for s in data["slots"]}

    s1 = by_slot[(AVAIL_DATE, AVAIL_HOUR)]
    assert s1["yes"] == 2
    assert s1["maybe"] == 1
    assert s1["no"] == 0
    assert s1["score"] == 2*2 + 1  # 5

    s2 = by_slot[(date2, AVAIL_HOUR)]
    assert s2["yes"] == 1
    assert s2["no"] == 1
    assert s2["score"] == 2 - 2  # 0


# ── cross-event isolation ─────────────────────────────────────────────────────

def test_same_name_isolated_across_events(client):
    e1 = _make_event(client, "Event One")["event_id"]
    e2 = _make_event(client, "Event Two")["event_id"]
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    r1 = client.post(f"/api/events/{e1}/submissions", json={
        "name": "Alex", "availability": avail,
    })
    r2 = client.post(f"/api/events/{e2}/submissions", json={
        "name": "Alex", "availability": avail,
    })
    assert r1.status_code == 201
    assert r2.status_code == 201

    # Each event has its own respondent count
    assert client.get(f"/api/events/{e1}/results").json()["respondent_count"] == 1
    assert client.get(f"/api/events/{e2}/results").json()["respondent_count"] == 1


# ── admin privacy ─────────────────────────────────────────────────────────────

def test_admin_cannot_see_respondent_names(client):
    event = _make_event(client)
    eid = event["event_id"]
    admin_token = event["admin_token"]
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    client.post(f"/api/events/{eid}/submissions", json={"name": "SecretPerson", "availability": avail})
    client.post(f"/api/events/{eid}/submissions", json={"name": "AnotherSecret", "availability": avail})

    admin_res = client.get(
        f"/api/events/{eid}/admin",
        headers={"X-Admin-Token": admin_token},
    )
    body = admin_res.text
    assert "SecretPerson" not in body
    assert "AnotherSecret" not in body
    assert admin_res.json()["respondent_count"] == 2


# ── delete cascade ────────────────────────────────────────────────────────────

def test_delete_event_removes_all_associated_data(client):
    event = _make_event(client)
    eid = event["event_id"]
    admin_token = event["admin_token"]
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    sub = client.post(f"/api/events/{eid}/submissions", json={
        "name": "Alice", "availability": avail,
    }).json()

    client.delete(f"/api/events/{eid}", headers={"X-Admin-Token": admin_token})

    assert client.get(f"/api/events/{eid}").status_code == 404
    assert client.get(f"/api/events/{eid}/results").status_code == 404


# ── inline registration during submission ────────────────────────────────────

def test_inline_register_and_subsequent_login(client):
    event = _make_event(client)
    eid = event["event_id"]
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    client.post(f"/api/events/{eid}/submissions", json={
        "name": "inlineuser",
        "availability": avail,
        "register": True,
        "email": "inline@example.com",
        "passphrase": "inlinepassword1",
    })

    # Can now log in with the inline-registered credentials
    login = client.post("/api/accounts/session", json={
        "username": "inlineuser",
        "passphrase": "inlinepassword1",
    })
    assert login.status_code == 200


# ── edit token uniqueness ─────────────────────────────────────────────────────

def test_two_ephemeral_users_get_different_edit_tokens(client):
    event = _make_event(client)
    eid = event["event_id"]
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    t1 = client.post(f"/api/events/{eid}/submissions", json={
        "name": "UserOne", "availability": avail,
    }).json()["edit_token"]
    t2 = client.post(f"/api/events/{eid}/submissions", json={
        "name": "UserTwo", "availability": avail,
    }).json()["edit_token"]

    assert t1 != t2


def test_edit_token_cannot_update_other_users_submission(client):
    event = _make_event(client)
    eid = event["event_id"]
    avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]

    alice_token = client.post(f"/api/events/{eid}/submissions", json={
        "name": "Alice", "availability": avail,
    }).json()["edit_token"]

    client.post(f"/api/events/{eid}/submissions", json={
        "name": "Bob", "availability": avail,
    })

    # Alice's token cannot update Bob's submission (wrong event/token combo would 401)
    # Actually, the token is tied to Alice's submission in this event — using it
    # will update Alice's submission, not Bob's. Here we verify token isolation.
    new_avail = [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "no"}]
    client.put(
        f"/api/events/{eid}/submissions",
        json={"availability": new_avail},
        headers={"X-Edit-Token": alice_token},
    )

    # Bob's submission should be unchanged (still "yes")
    results = client.get(f"/api/events/{eid}/results").json()
    total_yes = sum(s["yes"] for s in results["slots"])
    total_no = sum(s["no"] for s in results["slots"])
    assert total_yes == 1  # Bob still yes
    assert total_no == 1   # Alice now no
