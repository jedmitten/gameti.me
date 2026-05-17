import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from ..config import settings
from ..crypto import hash_passphrase, hash_token, hmac_username
from ..database import get_db

router = APIRouter(tags=["site-admin"])


class TransferUsernameRequest(BaseModel):
    username: str
    new_passphrase: str


@router.post("/site-admin/transfer-username")
async def transfer_username(
    body: TransferUsernameRequest,
    x_site_admin_secret: str = Header(alias="X-Site-Admin-Secret"),
):
    if not secrets.compare_digest(x_site_admin_secret, settings.site_admin_secret):
        raise HTTPException(status_code=403, detail="Invalid site admin secret")

    username = body.username.strip()
    username_hmac = hmac_username(username)

    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM accounts WHERE username_hmac = ?", (username_hmac,)
        ) as cursor:
            account = await cursor.fetchone()

        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")

        new_hash = hash_passphrase(body.new_passphrase)

        await db.execute(
            "UPDATE accounts SET passphrase_hash=? WHERE id=?",
            (new_hash, account["id"]),
        )

        await db.execute(
            "DELETE FROM account_sessions WHERE account_id=?", (account["id"],)
        )

        await db.commit()

    return {"message": "Username transferred successfully"}
