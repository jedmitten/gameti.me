import asyncio
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

# ── env vars must be set before any backend import ──────────────────────────
_tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = str(Path(_tmpdir) / "test.db")
os.environ.setdefault("SECRET_KEY", "a" * 64)
os.environ.setdefault("SITE_ADMIN_SECRET", "testadminsecret")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ["SMTP_HOST"] = ""  # always disable email in tests

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db
from backend.limiter import limiter

# Disable rate limiting in the test suite
limiter.enabled = False

# ── shared date constants ────────────────────────────────────────────────────
_TODAY = date.today()
WIN_START = (_TODAY + timedelta(days=1)).isoformat()
WIN_END = (_TODAY + timedelta(days=60)).isoformat()
AVAIL_DATE = (_TODAY + timedelta(days=5)).isoformat()
DAY_START = 8
DAY_END = 20
AVAIL_HOUR = 10  # within [DAY_START, DAY_END)

SITE_ADMIN_SECRET = "testadminsecret"


# ── helpers ──────────────────────────────────────────────────────────────────

def run(coro):
    return asyncio.run(coro)


def expire_event(event_id: str) -> None:
    """Force an event to appear expired in the DB."""
    async def _do():
        async with get_db() as db:
            await db.execute(
                "UPDATE events SET expires_at=? WHERE id=?",
                ("2020-01-01T00:00:00+00:00", event_id),
            )
            await db.commit()
    run(_do())


def set_recovery_token(account_id: str, token_hash: str, expires_iso: str) -> None:
    async def _do():
        async with get_db() as db:
            await db.execute(
                "UPDATE accounts SET recovery_token_hash=?, recovery_token_expires=? WHERE id=?",
                (token_hash, expires_iso, account_id),
            )
            await db.commit()
    run(_do())


def get_account_id_by_session(session_token: str) -> str:
    from backend.crypto import hash_token
    async def _do():
        async with get_db() as db:
            async with db.execute(
                "SELECT account_id FROM account_sessions WHERE token_hash=?",
                (hash_token(session_token),),
            ) as cur:
                row = await cur.fetchone()
        return row["account_id"]
    return run(_do())


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_db():
    async def _truncate():
        async with get_db() as db:
            await db.execute("DELETE FROM availability")
            await db.execute("DELETE FROM submissions")
            await db.execute("DELETE FROM account_sessions")
            await db.execute("DELETE FROM events")
            await db.execute("DELETE FROM accounts")
            await db.commit()
    run(_truncate())


@pytest.fixture
def event(client):
    res = client.post("/api/events", json={
        "title": "Test Event",
        "description": "A test event",
        "timezone": "America/Chicago",
        "window_start": WIN_START,
        "window_end": WIN_END,
        "day_start_hour": DAY_START,
        "day_end_hour": DAY_END,
    })
    assert res.status_code == 201
    return res.json()


@pytest.fixture
def event_id(event):
    return event["event_id"]


@pytest.fixture
def admin_token(event):
    return event["admin_token"]


@pytest.fixture
def account(client):
    res = client.post("/api/accounts", json={
        "username": "testuser",
        "email": "test@example.com",
        "passphrase": "securepassword123",
    })
    assert res.status_code == 201
    return res.json()


@pytest.fixture
def session_token(account):
    return account["session_token"]


@pytest.fixture
def avail_items():
    return [{"date": AVAIL_DATE, "hour": AVAIL_HOUR, "status": "yes"}]
