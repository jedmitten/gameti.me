import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..crypto import (
    decrypt,
    encrypt,
    generate_token,
    hash_passphrase,
    hash_token,
    hmac_username,
    verify_passphrase,
    verify_token,
)
from ..database import get_db
from ..config import settings
from ..email_service import send_recovery_email

router = APIRouter(tags=["accounts"])

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


async def _get_session_account(token: str, db) -> dict:
    token_hash = hash_token(token)
    async with db.execute(
        "SELECT account_id, expires_at FROM account_sessions WHERE token_hash = ?",
        (token_hash,),
    ) as cursor:
        session = await cursor.fetchone()

    if session is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session token")

    expiry = datetime.fromisoformat(session["expires_at"])
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expiry:
        raise HTTPException(status_code=401, detail="Session expired")

    async with db.execute(
        "SELECT * FROM accounts WHERE id = ?", (session["account_id"],)
    ) as cursor:
        account = await cursor.fetchone()

    if account is None:
        raise HTTPException(status_code=401, detail="Account not found")

    return account


class CheckUsernameRequest(BaseModel):
    username: str


class RegisterRequest(BaseModel):
    username: str
    email: str
    passphrase: str


class LoginRequest(BaseModel):
    username: str
    passphrase: str


class RecoveryRequest(BaseModel):
    username: str
    email: str


class RecoveryConfirmRequest(BaseModel):
    token: str
    new_passphrase: str


@router.post("/accounts/check-username")
async def check_username(body: CheckUsernameRequest):
    username_hmac = hmac_username(body.username)
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM accounts WHERE username_hmac = ?", (username_hmac,)
        ) as cursor:
            row = await cursor.fetchone()
    return {"available": row is None}


@router.post("/accounts", status_code=201)
async def register(body: RegisterRequest):
    username = body.username.strip()

    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3–50 characters: letters, digits, underscore, hyphen only",
        )

    if len(body.passphrase) < 8:
        raise HTTPException(status_code=422, detail="Passphrase must be at least 8 characters")

    username_hmac = hmac_username(username)

    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM accounts WHERE username_hmac = ?", (username_hmac,)
        ) as cursor:
            existing = await cursor.fetchone()

        if existing is not None:
            raise HTTPException(status_code=409, detail="Username already taken")

        now = datetime.now(tz=timezone.utc)
        account_id = str(uuid.uuid4())
        username_enc = encrypt(username)
        email_enc = encrypt(body.email.strip())
        passphrase_hash = hash_passphrase(body.passphrase)

        await db.execute(
            """
            INSERT INTO accounts
                (id, username_hmac, username_enc, email_enc, passphrase_hash, created_at, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                account_id,
                username_hmac,
                username_enc,
                email_enc,
                passphrase_hash,
                now.isoformat(),
                now.isoformat(),
            ),
        )

        session_token = generate_token()
        session_token_hash = hash_token(session_token)
        session_expires = (now + timedelta(days=30)).isoformat()

        await db.execute(
            """
            INSERT INTO account_sessions (token_hash, account_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_token_hash, account_id, now.isoformat(), session_expires),
        )

        await db.commit()

    return JSONResponse(
        status_code=201,
        content={"session_token": session_token, "username": username},
    )


@router.post("/accounts/session")
async def login(body: LoginRequest):
    username = body.username.strip()
    username_hmac = hmac_username(username)

    _bad_creds = HTTPException(status_code=401, detail="Invalid username or passphrase")

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM accounts WHERE username_hmac = ?", (username_hmac,)
        ) as cursor:
            account = await cursor.fetchone()

        if account is None:
            raise _bad_creds

        if not verify_passphrase(body.passphrase, account["passphrase_hash"]):
            raise _bad_creds

        now = datetime.now(tz=timezone.utc)
        session_token = generate_token()
        session_token_hash = hash_token(session_token)
        session_expires = (now + timedelta(days=30)).isoformat()

        await db.execute(
            """
            INSERT INTO account_sessions (token_hash, account_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_token_hash, account["id"], now.isoformat(), session_expires),
        )

        await db.execute(
            "UPDATE accounts SET last_seen=? WHERE id=?",
            (now.isoformat(), account["id"]),
        )

        await db.commit()

    return {"session_token": session_token, "username": decrypt(account["username_enc"])}


@router.delete("/accounts/session", status_code=204)
async def logout(
    x_session_token: str = Header(alias="X-Session-Token"),
):
    token_hash = hash_token(x_session_token)
    async with get_db() as db:
        await db.execute(
            "DELETE FROM account_sessions WHERE token_hash = ?", (token_hash,)
        )
        await db.commit()


@router.get("/accounts/me")
async def get_me(
    x_session_token: str = Header(alias="X-Session-Token"),
):
    async with get_db() as db:
        account = await _get_session_account(x_session_token, db)

    return {
        "username": decrypt(account["username_enc"]),
        "has_email": account["email_enc"] is not None,
    }


@router.get("/accounts/me/events")
async def get_my_events(
    x_session_token: str = Header(alias="X-Session-Token"),
):
    async with get_db() as db:
        account = await _get_session_account(x_session_token, db)

        async with db.execute(
            """
            SELECT s.event_id, s.created_at as submitted_at, e.title_enc, e.expires_at
            FROM submissions s
            JOIN events e ON e.id = s.event_id
            WHERE s.account_id = ?
            ORDER BY s.created_at DESC
            """,
            (account["id"],),
        ) as cursor:
            rows = await cursor.fetchall()

    result = []
    for row in rows:
        try:
            title = decrypt(row["title_enc"])
        except Exception:
            title = ""
        result.append(
            {
                "event_id": row["event_id"],
                "title": title,
                "submitted_at": row["submitted_at"],
                "share_url": f"{settings.base_url}/e/{row['event_id']}",
            }
        )

    return result


@router.post("/accounts/recovery", status_code=204)
async def request_recovery(body: RecoveryRequest):
    username = body.username.strip()
    username_hmac = hmac_username(username)
    provided_email = body.email.strip().lower()

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM accounts WHERE username_hmac = ?", (username_hmac,)
        ) as cursor:
            account = await cursor.fetchone()

        if account is not None and account["email_enc"] is not None:
            try:
                stored_email = decrypt(account["email_enc"]).strip().lower()
            except Exception:
                stored_email = None

            if stored_email == provided_email:
                recovery_token = generate_token()
                token_hash = hash_token(recovery_token)
                now = datetime.now(tz=timezone.utc)
                expires = (now + timedelta(minutes=15)).isoformat()

                await db.execute(
                    "UPDATE accounts SET recovery_token_hash=?, recovery_token_expires=? WHERE id=?",
                    (token_hash, expires, account["id"]),
                )
                await db.commit()

                recovery_url = f"{settings.base_url}/me#recover:{recovery_token}"
                decrypted_username = decrypt(account["username_enc"])
                await send_recovery_email(body.email.strip(), decrypted_username, recovery_url)


@router.post("/accounts/recovery/confirm")
async def confirm_recovery(body: RecoveryConfirmRequest):
    if len(body.new_passphrase) < 8:
        raise HTTPException(status_code=422, detail="Passphrase must be at least 8 characters")

    token_hash = hash_token(body.token)

    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM accounts WHERE recovery_token_hash = ?", (token_hash,)
        ) as cursor:
            account = await cursor.fetchone()

        if account is None:
            raise HTTPException(status_code=400, detail="Invalid or expired recovery token")

        expires = datetime.fromisoformat(account["recovery_token_expires"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(tz=timezone.utc) > expires:
            raise HTTPException(status_code=400, detail="Recovery token has expired")

        new_hash = hash_passphrase(body.new_passphrase)
        now = datetime.now(tz=timezone.utc).isoformat()

        await db.execute(
            """
            UPDATE accounts
            SET passphrase_hash=?, recovery_token_hash=NULL, recovery_token_expires=NULL, last_seen=?
            WHERE id=?
            """,
            (new_hash, now, account["id"]),
        )

        await db.execute(
            "DELETE FROM account_sessions WHERE account_id=?", (account["id"],)
        )

        session_token = generate_token()
        session_token_hash = hash_token(session_token)
        session_expires = (
            datetime.now(tz=timezone.utc) + timedelta(days=30)
        ).isoformat()

        await db.execute(
            """
            INSERT INTO account_sessions (token_hash, account_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (session_token_hash, account["id"], now, session_expires),
        )

        await db.commit()

    username = decrypt(account["username_enc"])
    return {"session_token": session_token, "username": username}
