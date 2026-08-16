"""
Database + local filesystem bootstrap for PUGA.

Everything here is path-relative to this file, so the backend works no
matter where the project folder lives on disk (no hardcoded
"D:\\THE PUGA PROJECT" anywhere). This module is safe to import multiple
times; init_storage() is idempotent.
"""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ---------------------------------------------------------------------------
# Paths (all relative to backend/, i.e. the parent of this app/ package)
# ---------------------------------------------------------------------------

APP_DIR = Path(__file__).resolve().parent          # backend/app
BACKEND_DIR = APP_DIR.parent                        # backend/

DATABASE_DIR = BACKEND_DIR / "database"
DATABASE_PATH = DATABASE_DIR / "puga.db"

DATA_DIR = BACKEND_DIR / "data"
IMAGES_DIR = DATA_DIR / "images"
CROPS_DIR = DATA_DIR / "crops"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"

SQLALCHEMY_DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# ---------------------------------------------------------------------------
# SQLAlchemy setup
# ---------------------------------------------------------------------------

# check_same_thread=False is required for SQLite + FastAPI's threaded
# request handling. This is a single-file local DB, not a network service.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def init_storage() -> None:
    """Create the database file, all tables, and all local data
    directories if they do not already exist. Called once on FastAPI
    startup. Safe to call repeatedly."""

    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    CROPS_DIR.mkdir(parents=True, exist_ok=True)
    EMBEDDINGS_DIR.mkdir(parents=True, exist_ok=True)

    # Import models here (not at module top) so all model classes are
    # registered on Base.metadata before create_all() runs, without
    # creating a circular import between database.py and models.py.
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI dependency that yields a request-scoped DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
