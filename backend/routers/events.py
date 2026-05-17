from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator, model_validator

from ..config import settings
from ..crypto import decrypt, encrypt, generate_token, hash_token, verify_token
from ..database import get_db

router = APIRouter(tags=["events"])


class CreateEventRequest(BaseModel):
    title: str
    description: Optional[str] = None
    timezone: str
    window_start: str
    window_end: str
    day_start_hour: int
    day_end_hour: int

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("title must not be empty")
        if len(v) > 200:
            raise ValueError("title must be 200 chars or fewer")
        return v

    @field_validator("description")
    @classmethod
    def validate_description(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if len(v) > 1000:
            raise ValueError("description must be 1000 chars or fewer")
        return v if v else None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        if len(v) > 100:
            raise ValueError("timezone must be 100 chars or fewer")
        return v

    @field_validator("day_start_hour")
    @classmethod
    def validate_day_start_hour(cls, v: int) -> int:
        if v < 0 or v > 22:
            raise ValueError("day_start_hour must be 0–22")
        return v

    @field_validator("day_end_hour")
    @classmethod
    def validate_day_end_hour(cls, v: int) -> int:
        if v < 1 or v > 23:
            raise ValueError("day_end_hour must be 1–23")
        return v

    @model_validator(mode="after")
    def validate_window_and_hours(self) -> "CreateEventRequest":
        if self.window_end < self.window_start:
            raise ValueError("window_end must be >= window_start")
        if self.day_end_hour <= self.day_start_hour:
            raise ValueError("day_end_hour must be > day_start_hour")
        return self


def _check_expired(expires_at: str) -> None:
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expiry:
        raise HTTPException(status_code=410, detail="Event has expired")


@router.post("/events", status_code=201)
async def create_event(body: CreateEventRequest):
    event_id = str(uuid.uuid4())
    admin_token = generate_token()
    admin_token_hash = hash_token(admin_token)
    now = datetime.now(tz=timezone.utc)
    expires_at = (now + timedelta(days=settings.event_expiry_days)).isoformat()
    created_at = now.isoformat()

    title_enc = encrypt(body.title)
    description_enc = encrypt(body.description) if body.description else None

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO events
                (id, title_enc, description_enc, timezone, window_start, window_end,
                 day_start_hour, day_end_hour, admin_token_hash, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                title_enc,
                description_enc,
                body.timezone,
                body.window_start,
                body.window_end,
                body.day_start_hour,
                body.day_end_hour,
                admin_token_hash,
                expires_at,
                created_at,
            ),
        )
        await db.commit()

    return JSONResponse(
        status_code=201,
        content={
            "event_id": event_id,
            "share_url": f"{settings.base_url}/e/{event_id}",
            "admin_token": admin_token,
        },
    )


@router.get("/events/{event_id}")
async def get_event(event_id: str):
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Event not found")

    _check_expired(row["expires_at"])

    return {
        "id": row["id"],
        "title": decrypt(row["title_enc"]),
        "description": decrypt(row["description_enc"]) if row["description_enc"] else None,
        "timezone": row["timezone"],
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "day_start_hour": row["day_start_hour"],
        "day_end_hour": row["day_end_hour"],
        "created_at": row["created_at"],
        "expires_at": row["expires_at"],
    }


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    event_id: str,
    x_admin_token: str = Header(alias="X-Admin-Token"),
):
    async with get_db() as db:
        async with db.execute(
            "SELECT admin_token_hash FROM events WHERE id = ?", (event_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Event not found")

        if not verify_token(x_admin_token, row["admin_token_hash"]):
            raise HTTPException(status_code=403, detail="Invalid admin token")

        await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await db.commit()


@router.get("/events/{event_id}/admin")
async def get_event_admin(
    event_id: str,
    x_admin_token: str = Header(alias="X-Admin-Token"),
):
    async with get_db() as db:
        async with db.execute(
            "SELECT admin_token_hash, window_start, window_end, expires_at FROM events WHERE id = ?",
            (event_id,),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            raise HTTPException(status_code=404, detail="Event not found")

        if not verify_token(x_admin_token, row["admin_token_hash"]):
            raise HTTPException(status_code=403, detail="Invalid admin token")

        _check_expired(row["expires_at"])

        async with db.execute(
            "SELECT COUNT(*) as cnt FROM submissions WHERE event_id = ?", (event_id,)
        ) as cursor:
            count_row = await cursor.fetchone()

    return {
        "respondent_count": count_row["cnt"],
        "window_start": row["window_start"],
        "window_end": row["window_end"],
        "expires_at": row["expires_at"],
    }
