"""Autonoma FastAPI application entrypoint.

Wires the routers, starts the orchestration engine on startup, and serves the
static command-center dashboard.
"""
from __future__ import annotations

import contextlib
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .api import agents, approvals, inference_mode, monitor, skills, tasks
from .config import get_settings
from .core.orchestrator import orchestrator

STATIC_DIR = Path(__file__).parent / "static"


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    get_settings().ensure_dirs()
    await orchestrator.start()
    try:
        yield
    finally:
        await orchestrator.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Autonoma Agent System",
        version=__version__,
        description="Original Manus-style multi-agent desktop-automation command center.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for r in (skills.router, tasks.router, agents.router,
              inference_mode.router, monitor.router, approvals.router):
        app.include_router(r)

    @app.get("/api/v1/health", tags=["meta"])
    def api_health():
        from .core import health
        return health.check()

    @app.get("/api/v1/info", tags=["meta"])
    def info():
        s = get_settings()
        return {
            "name": "Autonoma",
            "version": __version__,
            "automation_backend": s.automation_backend,
            "work_dir_configured": s.work_dir is not None,
        }

    if settings.serve_frontend and STATIC_DIR.exists():
        # Serve built React SPA if present; else the zero-build dashboard.
        dist = STATIC_DIR / "dist"
        root = dist if (dist / "index.html").exists() else STATIC_DIR

        @app.get("/", include_in_schema=False)
        def index():
            return FileResponse(root / "index.html")

        app.mount("/static", StaticFiles(directory=root), name="static")
    else:
        @app.get("/", include_in_schema=False)
        def index():
            return JSONResponse({"name": "Autonoma", "docs": "/docs"})

    return app


app = create_app()
