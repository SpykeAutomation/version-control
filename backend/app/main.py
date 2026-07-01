"""FastAPI application entry point: `uvicorn app.main:app`."""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401  (registers tables on Base)
from .config import settings
from .db import Base, engine
from .routers import auth, device_auth, orgs, projects, pulls, storage

_timing_log = logging.getLogger("app.timing")

# Create tables on startup. For a pilot this is enough; migrations can come
# later (Alembic) once the schema needs to evolve without data loss.
Base.metadata.create_all(engine)

app = FastAPI(
    title="PLC Version Control API",
    version="0.1.0",
    description="Semantic version control for Rockwell L5X PLC projects.",
)

_origins = (
    ["*"]
    if settings.cors_origins.strip() == "*"
    else [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    # Auth is via Bearer tokens, not cookies, so credentials aren't needed —
    # and "*" origins with credentials is rejected by browsers anyway.
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def _request_timing(request: Request, call_next):
    """Basic observability: log each request's status + wall time and expose it
    as a response header. This is the gauge for spotting saturation (rising
    p95, threadpool queueing) before users report it."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.0f}"
    _timing_log.info(
        "%s %s -> %d in %.0fms",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


app.include_router(auth.router)
app.include_router(device_auth.router)
app.include_router(orgs.router)
app.include_router(projects.router)
app.include_router(pulls.router)
app.include_router(storage.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok"}
