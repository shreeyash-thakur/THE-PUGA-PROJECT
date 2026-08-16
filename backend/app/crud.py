"""Plain DB access functions, kept separate from the route handlers."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from app import models, schemas


def _new_sighting_id() -> str:
    return f"SGT-{uuid.uuid4().hex[:10].upper()}"


# ---------------------------------------------------------------------------
# Tigers
# ---------------------------------------------------------------------------

def get_tiger(db: Session, tiger_id: str) -> Optional[models.Tiger]:
    return db.query(models.Tiger).filter(models.Tiger.tiger_id == tiger_id).first()


def get_tigers(db: Session, skip: int = 0, limit: int = 100) -> List[models.Tiger]:
    return db.query(models.Tiger).offset(skip).limit(limit).all()


def create_tiger(db: Session, tiger: schemas.TigerCreate) -> models.Tiger:
    db_tiger = models.Tiger(
        tiger_id=tiger.tiger_id,
        name=tiger.name,
        status=tiger.status,
        reference_image=tiger.reference_image,
    )
    db.add(db_tiger)
    db.commit()
    db.refresh(db_tiger)
    return db_tiger


def update_tiger(
    db: Session, tiger_id: str, update: schemas.TigerUpdate
) -> Optional[models.Tiger]:
    db_tiger = get_tiger(db, tiger_id)
    if db_tiger is None:
        return None

    for field, value in update.model_dump(exclude_unset=True).items():
        setattr(db_tiger, field, value)

    db_tiger.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(db_tiger)
    return db_tiger


def delete_tiger(db: Session, tiger_id: str) -> bool:
    db_tiger = get_tiger(db, tiger_id)
    if db_tiger is None:
        return False
    db.delete(db_tiger)
    db.commit()
    return True


# ---------------------------------------------------------------------------
# Cameras
# ---------------------------------------------------------------------------

def get_cameras(db: Session, skip: int = 0, limit: int = 100) -> List[models.Camera]:
    return db.query(models.Camera).offset(skip).limit(limit).all()


def get_camera(db: Session, camera_id: str) -> Optional[models.Camera]:
    return db.query(models.Camera).filter(models.Camera.camera_id == camera_id).first()


def create_camera(db: Session, camera: schemas.CameraCreate) -> models.Camera:
    db_camera = models.Camera(**camera.model_dump())
    db.add(db_camera)
    db.commit()
    db.refresh(db_camera)
    return db_camera


# ---------------------------------------------------------------------------
# Sightings
# ---------------------------------------------------------------------------

def get_sighting(db: Session, sighting_id: str) -> Optional[models.Sighting]:
    return (
        db.query(models.Sighting)
        .filter(models.Sighting.sighting_id == sighting_id)
        .first()
    )


def get_sightings(db: Session, skip: int = 0, limit: int = 100) -> List[models.Sighting]:
    return db.query(models.Sighting).offset(skip).limit(limit).all()


def get_sightings_for_tiger(
    db: Session, tiger_id: str, skip: int = 0, limit: int = 100
) -> List[models.Sighting]:
    return (
        db.query(models.Sighting)
        .filter(models.Sighting.tiger_id == tiger_id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_sighting(db: Session, sighting: schemas.SightingCreate) -> models.Sighting:
    data = sighting.model_dump()
    timestamp = data.pop("timestamp") or datetime.now(timezone.utc)
    # SQLite (via SQLAlchemy's DateTime) stores naive datetimes, so values
    # read back from the DB have no tzinfo. Normalize everything to naive
    # UTC here so later comparisons (first_seen/last_seen below) don't mix
    # aware and naive datetimes.
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)

    db_sighting = models.Sighting(
        sighting_id=_new_sighting_id(),
        timestamp=timestamp,
        **data,
    )
    db.add(db_sighting)

    # Keep the parent tiger's rollup fields in sync.
    tiger = get_tiger(db, sighting.tiger_id)
    if tiger is not None:
        tiger.total_sightings = (tiger.total_sightings or 0) + 1
        if tiger.first_seen is None or timestamp < tiger.first_seen:
            tiger.first_seen = timestamp
        if tiger.last_seen is None or timestamp > tiger.last_seen:
            tiger.last_seen = timestamp

    db.commit()
    db.refresh(db_sighting)
    return db_sighting


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------

def create_embedding(db: Session, embedding: schemas.EmbeddingCreate) -> models.Embedding:
    db_embedding = models.Embedding(**embedding.model_dump())
    db.add(db_embedding)
    db.commit()
    db.refresh(db_embedding)
    return db_embedding


def get_embeddings_for_tiger(db: Session, tiger_id: str) -> List[models.Embedding]:
    return (
        db.query(models.Embedding).filter(models.Embedding.tiger_id == tiger_id).all()
    )


def get_all_embeddings(db: Session) -> List[models.Embedding]:
    """All stored embeddings, used to compare a new embedding against the
    existing gallery. Fine at hackathon/demo scale (SQLite, no index
    needed); would want a proper vector index before this grows large."""
    return db.query(models.Embedding).all()


def get_embedding_for_sighting(
    db: Session, sighting_id: str
) -> Optional[models.Embedding]:
    return (
        db.query(models.Embedding)
        .filter(models.Embedding.sighting_id == sighting_id)
        .first()
    )


def generate_unique_tiger_id(db: Session) -> str:
    """Generate a fresh, human-readable TIGER-xxxx id that doesn't
    collide with an existing one."""
    while True:
        candidate = f"TIGER-{uuid.uuid4().hex[:6].upper()}"
        if get_tiger(db, candidate) is None:
            return candidate
