from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .routers import accounts, events, results, site_admin, submissions


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="OurTime", lifespan=lifespan, docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
