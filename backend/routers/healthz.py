from fastapi import APIRouter, HTTPException

from ..database import get_db

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz():
    """Liveness + DB connectivity check used by the container healthcheck."""
    try:
        async with get_db() as db:
            await db.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
    return {"status": "ok"}
