"""Seed the database with initial game data.

Reads JSON seed files from ``game_data/seed/`` and inserts them into the
PostgreSQL database via SQLAlchemy.

Usage::

    python scripts/seed_data.py            # uses DATABASE_URL from .env
    python scripts/seed_data.py --db-url sqlite:///local.db
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = PROJECT_ROOT / "game_data" / "seed"

sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# SQLAlchemy table definitions (self-contained fallback)
# ---------------------------------------------------------------------------

try:
    from sqlalchemy import (
        Column,
        DateTime,
        Integer,
        String,
        Text,
        create_engine,
    )
    from sqlalchemy.orm import Session, declarative_base, sessionmaker
except ImportError:
    print("ERROR: sqlalchemy is not installed.  Run:  pip install sqlalchemy")
    sys.exit(1)

Base = declarative_base()


class ContentRecord(Base):  # type: ignore[misc]
    """Generic content table for seed data (items, monsters, quests)."""

    __tablename__ = "content_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_type = Column(String(50), nullable=False, index=True)
    content_id = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    data_json = Column(Text, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(20), nullable=False, default="approved")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


# Try to import the project's own models if available
try:
    from src.storage.models import Base as ProjectBase, ContentVersion  # noqa: F811

    USE_PROJECT_MODELS = True
except ImportError:
    USE_PROJECT_MODELS = False


# ---------------------------------------------------------------------------
# Seed loading helpers
# ---------------------------------------------------------------------------

def _load_seed_file(filename: str) -> list[dict]:
    """Load a JSON seed file, returning an empty list if it doesn't exist."""
    path = SEED_DIR / filename
    if not path.exists():
        print(f"  [SKIP] {path} not found")
        return []
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, list):
        return data
    return [data]


SEED_FILES = {
    "item": "items.json",
    "monster": "monsters.json",
    "quest": "quests.json",
}


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------

def create_tables(engine) -> None:
    """Create all tables if they don't already exist."""
    if USE_PROJECT_MODELS:
        ProjectBase.metadata.create_all(engine)
    else:
        Base.metadata.create_all(engine)
    print("[OK] Tables created / verified.")


def seed_content(session: Session) -> int:
    """Load seed data and insert into the database.

    Returns the total number of records inserted.
    """
    total = 0
    for content_type, filename in SEED_FILES.items():
        records = _load_seed_file(filename)
        if not records:
            continue

        print(f"  Loading {len(records)} {content_type}(s) from {filename} ...")
        for rec in records:
            content_id = rec.get("id", f"{content_type}_{total}")
            name = rec.get("name", rec.get("title", content_id))

            if USE_PROJECT_MODELS:
                obj = ContentVersion(
                    content_type=content_type,
                    content_id=content_id,
                    version=1,
                    status="approved",
                    data=rec,
                    created_at=datetime.now(timezone.utc),
                )
            else:
                obj = ContentRecord(
                    content_type=content_type,
                    content_id=content_id,
                    name=name,
                    data_json=json.dumps(rec, ensure_ascii=False),
                    version=1,
                    status="approved",
                )

            # Skip if already present
            existing = (
                session.query(ContentRecord if not USE_PROJECT_MODELS else ContentVersion)
                .filter_by(content_id=content_id)
                .first()
            )
            if existing:
                print(f"    [SKIP] {content_id} already exists")
                continue

            session.add(obj)
            total += 1

    session.commit()
    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the game content database")
    parser.add_argument(
        "--db-url",
        default=None,
        help="SQLAlchemy database URL (default: from .env or sqlite:///game_content.db)",
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before seeding (WARNING: destructive)",
    )
    args = parser.parse_args()

    # Resolve database URL
    db_url = args.db_url
    if db_url is None:
        try:
            from src.config import get_settings
            db_url = get_settings().database_url
        except Exception:
            db_url = "sqlite:///game_content.db"
            print(f"  [INFO] Using fallback database: {db_url}")

    print(f"Database: {db_url}")
    engine = create_engine(db_url, echo=False)

    if args.drop:
        print("[WARN] Dropping all tables ...")
        if USE_PROJECT_MODELS:
            ProjectBase.metadata.drop_all(engine)
        else:
            Base.metadata.drop_all(engine)

    create_tables(engine)

    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        count = seed_content(session)

    print(f"\n[DONE] Seeded {count} record(s) into the database.")


if __name__ == "__main__":
    main()
