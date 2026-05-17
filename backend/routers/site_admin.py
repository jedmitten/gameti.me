import logging
import secrets

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from ..config import settings
from ..crypto import hash_passphrase, hash_token, hmac_username
from ..database import get_db
from ..limiter import limiter

router = APIRouter(tags=["site-admin"])
logger = logging.getLogger(__name__)


class TransferUsernameRequest(BaseModel):
    username: str
    new_passphrase: str


@router.post("/site-admin/transfer-username")
@limiter.limit("5/minute")
async def transfer_username(
    request: Request,
    body: TransferUsernameRequest,
    x_site_admin_secret: str = Header(alias="X-Site-Admin-Secret"),
):
    if not secrets.compare_digest(x_site_admin_secret, settings.site_admin_secret):
        logger.warning("site-admin: failed auth attempt for transfer-username")
        raise HTTPException(status_code=403, detail="Invalid site admin secret")

    username = body.username.strip()
    username_hmac = hmac_username(username)

    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM accounts WHERE username_hmac = ?", (username_hmac,)
        ) as cursor:
            account = await cursor.fetchone()

        if account is None:
            logger.warning("site-admin: transfer-username — account not found for supplied username")
            raise HTTPException(status_code=404, detail="Account not found")

        new_hash = await run_in_threadpool(hash_passphrase, body.new_passphrase)

        await db.execute(
            "UPDATE accounts SET passphrase_hash=? WHERE id=?",
            (new_hash, account["id"]),
        )

        await db.execute(
            "DELETE FROM account_sessions WHERE account_id=?", (account["id"],)
        )

        await db.commit()

    logger.info("site-admin: transfer-username succeeded for account %s", account["id"])
    return {"message": "Username transferred successfully"}
