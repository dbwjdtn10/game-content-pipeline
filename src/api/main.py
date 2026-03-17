"""FastAPI application entry point."""

from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from src.api.middleware import RateLimitMiddleware, RequestIDMiddleware
from src.config import get_settings
from src.storage.models import Base

logger = structlog.get_logger(__name__)
settings = get_settings()

_start_time: float = 0.0

# ------------------------------------------------------------------
# Database setup
# ------------------------------------------------------------------

engine = create_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Session:  # type: ignore[misc]
    """Dependency that yields a SQLAlchemy session and closes it afterwards."""
    db = SessionLocal()
    try:
        yield db  # type: ignore[misc]
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ------------------------------------------------------------------
# Lifespan
# ------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: create tables on startup."""
    global _start_time
    _start_time = time.time()
    logger.info("api.startup", database_url=settings.database_url[:30] + "...")
    Base.metadata.create_all(bind=engine)
    yield
    logger.info("api.shutdown")


# ------------------------------------------------------------------
# App factory
# ------------------------------------------------------------------

app = FastAPI(
    title="Game Content Pipeline API",
    version="0.1.0",
    description="API for AI-powered game content generation and management",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware (order matters: first added = outermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware, max_requests=100, window_seconds=60)
app.add_middleware(RequestIDMiddleware)


# ------------------------------------------------------------------
# Global exception handler
# ------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions and return a structured JSON error."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "unhandled_exception",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
    )


# ------------------------------------------------------------------
# Register routers (versioned under /api/v1)
# ------------------------------------------------------------------

from src.api.routes.content import router as content_router  # noqa: E402
from src.api.routes.pipeline import router as pipeline_router  # noqa: E402
from src.api.routes.stats import router as stats_router  # noqa: E402

API_V1 = "/api/v1"

app.include_router(content_router, prefix=f"{API_V1}/content", tags=["content"])
app.include_router(pipeline_router, prefix=f"{API_V1}/pipeline", tags=["pipeline"])
app.include_router(stats_router, prefix=f"{API_V1}/stats", tags=["stats"])

# Backward-compatible routes (without /api/v1 prefix)
app.include_router(content_router, prefix="/content", tags=["content"], include_in_schema=False)
app.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"], include_in_schema=False)
app.include_router(stats_router, prefix="/stats", tags=["stats"], include_in_schema=False)


# ------------------------------------------------------------------
# Health check
# ------------------------------------------------------------------


def _check_db() -> dict[str, Any]:
    """Test database connectivity."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


def _check_redis() -> dict[str, Any]:
    """Test Redis connectivity."""
    try:
        import redis

        r = redis.from_url(settings.redis_url, socket_connect_timeout=2)
        r.ping()
        return {"status": "healthy"}
    except Exception as exc:
        return {"status": "unhealthy", "error": str(exc)}


@app.get("/health")
def health_check() -> dict[str, Any]:
    """Basic liveness probe."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check() -> JSONResponse:
    """Deep readiness probe: checks DB + Redis connectivity."""
    db_status = _check_db()
    redis_status = _check_redis()

    all_healthy = (
        db_status["status"] == "healthy" and redis_status["status"] == "healthy"
    )
    uptime_seconds = round(time.time() - _start_time, 1) if _start_time else 0

    body = {
        "status": "ready" if all_healthy else "degraded",
        "uptime_seconds": uptime_seconds,
        "checks": {
            "database": db_status,
            "redis": redis_status,
        },
    }
    return JSONResponse(
        content=body,
        status_code=200 if all_healthy else 503,
    )
