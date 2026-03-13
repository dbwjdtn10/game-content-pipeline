"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import get_settings
from src.storage.models import Base

logger = structlog.get_logger(__name__)
settings = get_settings()

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
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------------------------------------------------------
# Register routers
# ------------------------------------------------------------------

from src.api.routes.content import router as content_router  # noqa: E402
from src.api.routes.pipeline import router as pipeline_router  # noqa: E402
from src.api.routes.stats import router as stats_router  # noqa: E402

app.include_router(content_router, prefix="/content", tags=["content"])
app.include_router(pipeline_router, prefix="/pipeline", tags=["pipeline"])
app.include_router(stats_router, prefix="/stats", tags=["stats"])


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
