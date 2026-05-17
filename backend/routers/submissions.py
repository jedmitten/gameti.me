from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..crypto import (
    decrypt,
    encrypt,
    generate_token,
    hash_passphrase,
    hash_token,
    hmac_name_in_event,
    hmac_username,
    verify_token,
)
from ..database import get_db

router = APIRouter(tags=["submissions"])


class AvailabilityItem(BaseModel):
    date: str
    hour: int
    status: str


class SubmitRequest(BaseModel):
    model_config = {"populate_by_name": True}

    name: str
    availability: list[AvailabilityItem]
    create_account: bool = Field(default=False, alias="register")
    email: Optional[str] = None
    passphrase: Optional[str] = None


class UpdateAvailabilityRequest(BaseModel):
    availability: list[AvailabilityItem]


def _validate_availability(items: list[AvailabilityItem], event_row) -> None:
    window_start = event_row["window_start"]
    window_end = event_row["window_end"]
    day_start = event_row["day_start_hour"]
    day_end = event_row["day_end_hour"]

    for item in items:
        if item.status not in ("yes", "maybe", "no"):
            raise HTTPException(status_code=422, detail=f"Invalid status: {item.status}")
        if item.hour < 0 or item.hour > 23:
            raise HTTPException(status_code=422, detail=f"Invalid hour: {item.hour}")
        if not (window_start <= item.date <= window_end):
            raise HTTPException(
                status_code=422,
                detail=f"Date {item.date} is outside event window",
            )
        if item.hour < day_start or item.hour >= day_end:
            raise HTTPException(
                status_code=422,
                detail=f"Hour {item.hour} is outside event day hours",
            )


def _check_expired(expires_at: str) -> None:
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expiry:
        raise HTTPException(status_code=410, detail="Event has expired")


@router.post("/events/{event_id}/submissions", status_code=201)
async def create_submission(
    event_id: str,
    body: SubmitRequest,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
):
    async with get_db() as db:
        # Fetch event
        async with db.execute("SELECT * FROM events WHERE id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()

        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")

        _check_expired(event["expires_at"])
        _validate_availability(body.availability, event)

        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name must not be empty")

        account_id: Optional[str] = None
        now = datetime.now(tz=timezone.utc).isoformat()

        # Determine identity
        if x_session_token:
            token_hash = hash_token(x_session_token)
            async with db.execute(
                "SELECT account_id, expires_at FROM account_sessions WHERE token_hash = ?",
                (token_hash,),
            ) as cursor:
                session = await cursor.fetchone()

            if session is None:
                raise HTTPException(status_code=401, detail="Invalid session token")

            session_expiry = datetime.fromisoformat(session["expires_at"])
            if session_expiry.tzinfo is None:
                session_expiry = session_expiry.replace(tzinfo=timezone.utc)
            if datetime.now(tz=timezone.utc) > session_expiry:
                raise HTTPException(status_code=401, detail="Session expired")

            account_id = session["account_id"]

        elif body.create_account and body.email and body.passphrase:
            # Inline registration
            if len(body.passphrase) < 8:
                raise HTTPException(status_code=422, detail="passphrase must be at least 8 characters")

            new_username_hmac = hmac_username(name)
            async with db.execute(
                "SELECT id FROM accounts WHERE username_hmac = ?", (new_username_hmac,)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                raise HTTPException(status_code=409, detail="Username already taken")

            new_account_id = str(uuid.uuid4())
            username_enc = encrypt(name)
            email_enc = encrypt(body.email)
            passphrase_hash = hash_passphrase(body.passphrase)

            await db.execute(
                """
                INSERT INTO accounts
                    (id, username_hmac, username_enc, email_enc, passphrase_hash, created_at, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (new_account_id, new_username_hmac, username_enc, email_enc, passphrase_hash, now, now),
            )
            account_id = new_account_id

        # For ephemeral path: check if name is a registered username
        if account_id is None:
            async with db.execute(
                "SELECT id FROM accounts WHERE username_hmac = ?",
                (hmac_username(name),),
            ) as cursor:
                name_account = await cursor.fetchone()

            if name_account is not None:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "registered": True,
                        "message": "This name is registered. Sign in to use it or choose a different name.",
                    },
                )

        name_hmac = hmac_name_in_event(name, event_id)

        # Check for existing submission
        async with db.execute(
            "SELECT id, account_id, edit_token_hash FROM submissions WHERE event_id=? AND name_hmac=?",
            (event_id, name_hmac),
        ) as cursor:
            existing_sub = await cursor.fetchone()

        edit_token: Optional[str] = None
        submission_id: str

        if existing_sub is not None:
            # Verify ownership
            can_edit = False
            if account_id and existing_sub["account_id"] == account_id:
                can_edit = True
            elif account_id is None and existing_sub["edit_token_hash"] is None:
                # Old account-linked submission, can't overwrite without auth
                can_edit = False
            # If the existing sub has no account and no edit token hash, it's an orphan — allow overwrite
            elif existing_sub["account_id"] is None and existing_sub["edit_token_hash"] is None:
                can_edit = True

            if not can_edit:
                raise HTTPException(status_code=409, detail="Name already taken in this event")

            submission_id = existing_sub["id"]

            # For ephemeral re-submissions, generate a new edit token
            if account_id is None:
                edit_token = generate_token()
                new_edit_token_hash = hash_token(edit_token)
            else:
                new_edit_token_hash = None

            await db.execute(
                "UPDATE submissions SET account_id=?, edit_token_hash=?, updated_at=? WHERE id=?",
                (account_id, new_edit_token_hash, now, submission_id),
            )
            await db.execute("DELETE FROM availability WHERE submission_id=?", (submission_id,))
        else:
            submission_id = str(uuid.uuid4())

            if account_id is None:
                edit_token = generate_token()
                edit_token_hash: Optional[str] = hash_token(edit_token)
            else:
                edit_token_hash = None

            await db.execute(
                """
                INSERT INTO submissions
                    (id, event_id, account_id, name_hmac, edit_token_hash, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (submission_id, event_id, account_id, name_hmac, edit_token_hash, now, now),
            )

        # Insert availability rows
        for item in body.availability:
            await db.execute(
                "INSERT INTO availability (submission_id, avail_date, hour, status) VALUES (?, ?, ?, ?)",
                (submission_id, item.date, item.hour, item.status),
            )

        await db.commit()

    return JSONResponse(
        status_code=201,
        content={"submission_id": submission_id, "edit_token": edit_token},
    )


@router.put("/events/{event_id}/submissions", status_code=200)
async def update_submission(
    event_id: str,
    body: UpdateAvailabilityRequest,
    x_edit_token: Optional[str] = Header(default=None, alias="X-Edit-Token"),
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
):
    if not x_edit_token and not x_session_token:
        raise HTTPException(status_code=401, detail="X-Edit-Token or X-Session-Token required")

    async with get_db() as db:
        async with db.execute("SELECT * FROM events WHERE id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()

        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")

        _check_expired(event["expires_at"])
        _validate_availability(body.availability, event)

        now = datetime.now(tz=timezone.utc).isoformat()
        submission_id: Optional[str] = None

        if x_session_token:
            token_hash = hash_token(x_session_token)
            async with db.execute(
                "SELECT account_id, expires_at FROM account_sessions WHERE token_hash = ?",
                (token_hash,),
            ) as cursor:
                session = await cursor.fetchone()

            if session is None:
                raise HTTPException(status_code=401, detail="Invalid session token")

            session_expiry = datetime.fromisoformat(session["expires_at"])
            if session_expiry.tzinfo is None:
                session_expiry = session_expiry.replace(tzinfo=timezone.utc)
            if datetime.now(tz=timezone.utc) > session_expiry:
                raise HTTPException(status_code=401, detail="Session expired")

            async with db.execute(
                "SELECT id FROM submissions WHERE event_id=? AND account_id=?",
                (event_id, session["account_id"]),
            ) as cursor:
                sub = await cursor.fetchone()

            if sub is None:
                raise HTTPException(status_code=404, detail="No submission found for this account")

            submission_id = sub["id"]

        elif x_edit_token:
            edit_token_hash = hash_token(x_edit_token)
            async with db.execute(
                "SELECT id FROM submissions WHERE event_id=? AND edit_token_hash=?",
                (event_id, edit_token_hash),
            ) as cursor:
                sub = await cursor.fetchone()

            if sub is None:
                raise HTTPException(status_code=401, detail="Invalid edit token")

            submission_id = sub["id"]

        await db.execute("DELETE FROM availability WHERE submission_id=?", (submission_id,))

        for item in body.availability:
            await db.execute(
                "INSERT INTO availability (submission_id, avail_date, hour, status) VALUES (?, ?, ?, ?)",
                (submission_id, item.date, item.hour, item.status),
            )

        await db.execute(
            "UPDATE submissions SET updated_at=? WHERE id=?", (now, submission_id)
        )
        await db.commit()

    return {"submission_id": submission_id}


@router.get("/events/{event_id}/submissions/me")
async def get_my_submission(
    event_id: str,
    x_edit_token: Optional[str] = Header(default=None, alias="X-Edit-Token"),
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
):
    if not x_edit_token and not x_session_token:
        raise HTTPException(status_code=401, detail="X-Edit-Token or X-Session-Token required")

    async with get_db() as db:
        async with db.execute("SELECT * FROM events WHERE id = ?", (event_id,)) as cursor:
            event = await cursor.fetchone()

        if event is None:
            raise HTTPException(status_code=404, detail="Event not found")

        submission_id: Optional[str] = None

        if x_session_token:
            token_hash = hash_token(x_session_token)
            async with db.execute(
                "SELECT account_id, expires_at FROM account_sessions WHERE token_hash = ?",
                (token_hash,),
            ) as cursor:
                session = await cursor.fetchone()

            if session is None:
                raise HTTPException(status_code=401, detail="Invalid session token")

            session_expiry = datetime.fromisoformat(session["expires_at"])
            if session_expiry.tzinfo is None:
                session_expiry = session_expiry.replace(tzinfo=timezone.utc)
            if datetime.now(tz=timezone.utc) > session_expiry:
                raise HTTPException(status_code=401, detail="Session expired")

            async with db.execute(
                "SELECT id FROM submissions WHERE event_id=? AND account_id=?",
                (event_id, session["account_id"]),
            ) as cursor:
                sub = await cursor.fetchone()

            if sub is None:
                raise HTTPException(status_code=404, detail="No submission found")

            submission_id = sub["id"]

        elif x_edit_token:
            edit_token_hash = hash_token(x_edit_token)
            async with db.execute(
                "SELECT id FROM submissions WHERE event_id=? AND edit_token_hash=?",
                (event_id, edit_token_hash),
            ) as cursor:
                sub = await cursor.fetchone()

            if sub is None:
                raise HTTPException(status_code=401, detail="Invalid edit token")

            submission_id = sub["id"]

        async with db.execute(
            "SELECT avail_date, hour, status FROM availability WHERE submission_id=?",
            (submission_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    return {
        "availability": [
            {"date": r["avail_date"], "hour": r["hour"], "status": r["status"]}
            for r in rows
        ]
    }
