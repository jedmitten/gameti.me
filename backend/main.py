from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .database import init_db
from .limiter import limiter
from .routers import accounts, events, results, site_admin, submissions
from .routers import healthz as healthz_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="OurTime",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.base_url],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Session-Token", "X-Edit-Token", "X-Admin-Token", "X-Site-Admin-Secret"],
)


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response


app.add_middleware(_SecurityHeadersMiddleware)

app.include_router(healthz_router.router)
app.include_router(events.router, prefix="/api")
app.include_router(submissions.router, prefix="/api")
app.include_router(results.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(site_admin.router, prefix="/api")

FRONTEND = Path(__file__).parent.parent / "frontend"

app.mount("/static", StaticFiles(directory=str(FRONTEND / "static")), name="static")


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/e/{event_id}")
async def event_page(event_id: str):
    return FileResponse(FRONTEND / "event.html")


@app.get("/admin/{event_id}")
async def admin_page(event_id: str):
    return FileResponse(FRONTEND / "admin.html")


@app.get("/me")
async def me_page():
    return FileResponse(FRONTEND / "me.html")
