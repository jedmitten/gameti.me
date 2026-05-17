"""Tests for the aggregate results endpoint."""
from tests.conftest import AVAIL_DATE, AVAIL_HOUR, DAY_START, WIN_START, WIN_END, DAY_END, expire_event
from datetime import date, timedelta


def _submit(client, event_id, name, items):
    return client.post(f"/api/events/{event_id}/submissions", json={
        "name": name, "availability": items,
    })


def test_results_empty_event(client, event_id):
    res = client.get(f"/api/events/{event_id}/results")
    assert res.status_code == 200
    data = res.json()
    assert data["respondent_count"] == 0
    assert data["slots"] == []


def test_results_event_not_found(client):
    res = client.get("/api/events/does-not-exist/results")
    assert res.status_code == 404


def test_results_single_submission(client, event_id):
    _submit(client, event_id, "Alice", [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"},
    ])
    res = client.get(f"/api/events/{event_id}/results")
    data = res.json()
    assert data["respondent_count"] == 1
    assert len(data["slots"]) == 1
    slot = data["slots"][0]
    assert slot["date"] == AVAIL_DATE
    assert slot["hour"] == AVAIL_HOUR
    assert slot["yes"] == 1
    assert slot["maybe"] == 0
    assert slot["no"] == 0


def test_results_score_formula_yes(client, event_id):
    _submit(client, event_id, "Alice", [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"},
    ])
    slot = client.get(f"/api/events/{event_id}/results").json()["slots"][0]
    assert slot["score"] == 2  # yes * 2


def test_results_score_formula_maybe(client, event_id):
    _submit(client, event_id, "Alice", [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "maybe"},
    ])
    slot = client.get(f"/api/events/{event_id}/results").json()["slots"][0]
    assert slot["score"] == 1  # maybe * 1


def test_results_score_formula_no(client, event_id):
    _submit(client, event_id, "Alice", [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "no"},
    ])
    slot = client.get(f"/api/events/{event_id}/results").json()["slots"][0]
    assert slot["score"] == -2  # no * -2


def test_results_score_formula_mixed(client, event_id):
    # 2 yes (score +4), 1 maybe (+1), 1 no (-2) = 3
    _submit(client, event_id, "Alice", [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}])
    _submit(client, event_id, "Bob",   [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}])
    _submit(client, event_id, "Carol", [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "maybe"}])
    _submit(client, event_id, "Dave",  [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "no"}])

    slot = client.get(f"/api/events/{event_id}/results").json()["slots"][0]
    assert slot["yes"] == 2
    assert slot["maybe"] == 1
    assert slot["no"] == 1
    assert slot["score"] == 4 + 1 - 2  # 3


def test_results_respondent_count(client, event_id, avail_items):
    _submit(client, event_id, "Alice", avail_items)
    _submit(client, event_id, "Bob",   avail_items)
    _submit(client, event_id, "Carol", avail_items)
    data = client.get(f"/api/events/{event_id}/results").json()
    assert data["respondent_count"] == 3


def test_results_sorted_by_score_desc(client, event_id):
    date2 = (date.fromisoformat(AVAIL_DATE) + timedelta(days=1)).isoformat()
    _submit(client, event_id, "Alice", [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "no"},    # score -2
        {"date": date2,      "hour": AVAIL_HOUR, "status": "yes"},   # score  2
    ])
    slots = client.get(f"/api/events/{event_id}/results").json()["slots"]
    assert slots[0]["score"] >= slots[-1]["score"]
    assert slots[0]["date"] == date2


def test_results_multiple_hours_per_day(client, event_id):
    _submit(client, event_id, "Alice", [
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR,     "status": "yes"},
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR + 1, "status": "maybe"},
        {"date": AVAIL_DATE, "hour": AVAIL_HOUR + 2, "status": "no"},
    ])
    data = client.get(f"/api/events/{event_id}/results").json()
    assert len(data["slots"]) == 3


def test_results_returns_410_for_expired_event(client, event_id, avail_items):
    _submit(client, event_id, "Alice", avail_items)
    expire_event(event_id)
    res = client.get(f"/api/events/{event_id}/results")
    assert res.status_code == 410


def test_results_independent_per_event(client, avail_items):
    def make_event():
        r = client.post("/api/events", json={
            "title": "Evt", "timezone": "UTC",
            "window_start": WIN_START, "window_end": WIN_END,
            "day_start_hour": DAY_START, "day_end_hour": DAY_END,
        })
        return r.json()["event_id"]

    eid1 = make_event()
    eid2 = make_event()
    _submit(client, eid1, "Alice", avail_items)

    data1 = client.get(f"/api/events/{eid1}/results").json()
    data2 = client.get(f"/api/events/{eid2}/results").json()
    assert data1["respondent_count"] == 1
    assert data2["respondent_count"] == 0
