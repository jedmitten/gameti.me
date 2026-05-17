"""Shared time and input-validation utilities used across routers."""
import re
from datetime import datetime, timezone

from fastapi import HTTPException

# P2-15: use \A / \Z anchors — $ matches before trailing \n in Python
_USERNAME_RE = re.compile(r"\A[a-zA-Z0-9_-]{3,50}\Z")


def check_expired(expires_at: str) -> None:
    expiry = datetime.fromisoformat(expires_at)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if datetime.now(tz=timezone.utc) > expiry:
        raise HTTPException(status_code=410, detail="Event has expired")


def validate_username(username: str) -> str:
    """Strip, reject CRLF, enforce regex. Returns normalised username."""
    username = username.strip()
    if "\r" in username or "\n" in username:
        raise HTTPException(status_code=422, detail="Username may not contain line breaks")
    if not _USERNAME_RE.match(username):
        raise HTTPException(
            status_code=422,
            detail="Username must be 3–50 characters: letters, digits, underscore, hyphen only",
        )
    return username


def validate_email(email: str) -> str:
    """Strip, reject CRLF, basic structural check. Returns normalised email."""
    email = email.strip()
    if "\r" in email or "\n" in email:
        raise HTTPException(status_code=422, detail="Email may not contain line breaks")
    at = email.find("@")
    if at < 1 or at == len(email) - 1 or len(email) > 254:
        raise HTTPException(status_code=422, detail="Invalid email address")
    return email
