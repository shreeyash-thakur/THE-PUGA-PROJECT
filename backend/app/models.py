"""
SQLAlchemy ORM models for the PUGA offline backend.

    Tiger
     |-- many Sightings
     `-- many Embeddings

    Camera
     `-- many Sightings

    Sighting
     |-- belongs to Tiger
     |-- belongs to Camera (optional)
     `-- can have one Embedding

These tables only store metadata + local filesystem paths. Image bytes,
crops, and embedding tensors (.pt files) live on disk under backend/data/,
never as blobs in SQLite.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid_suffix() -> str:
    return uuid.uuid4().hex[:8]


def _now() -> datetime:
    # Naive UTC, to match what SQLite/SQLAlchemy round-trips back out of
    # the DateTime column (see note in crud.create_sighting).
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Tiger(Base):
    __tablename__ = "tigers"

    id = Column(Integer, primary_key=True, index=True)

    # Human-readable unique identifier, e.g. "TIGER-001". This is what the
    # rest of the system (sightings, embeddings, API paths) refers to --
    # the integer `id` is just the DB primary key.
    tiger_id = Column(String, unique=True, index=True, nullable=False)

    name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="active")  # active/unknown/archived

    first_seen = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    total_sightings = Column(Integer, nullable=False, default=0)

    reference_image = Column(String, nullable=True)  # relative path under data/

    created_at = Column(DateTime, default=_now, nullable=False)
    updated_at = Column(DateTime, default=_now, onupdate=_now, nullable=False)

    sightings = relationship(
        "Sighting", back_populates="tiger", cascade="all, delete-orphan"
    )
    embeddings = relationship(
        "Embedding", back_populates="tiger", cascade="all, delete-orphan"
    )


class Camera(Base):
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, unique=True, index=True, nullable=False)

    name = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String, nullable=True)

    created_at = Column(DateTime, default=_now, nullable=False)

    sightings = relationship("Sighting", back_populates="camera")


class Sighting(Base):
    __tablename__ = "sightings"

    id = Column(Integer, primary_key=True, index=True)
    sighting_id = Column(String, unique=True, index=True, nullable=False)

    tiger_id = Column(String, ForeignKey("tigers.tiger_id"), nullable=False)
    camera_id = Column(String, ForeignKey("cameras.camera_id"), nullable=True)

    image_path = Column(String, nullable=True)      # relative path under data/images
    crop_path = Column(String, nullable=True)        # relative path under data/crops
    embedding_path = Column(String, nullable=True)   # relative path under data/embeddings

    similarity_score = Column(Float, nullable=True)
    confidence = Column(Float, nullable=True)

    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String, nullable=True)

    timestamp = Column(DateTime, default=_now, nullable=False)
    created_at = Column(DateTime, default=_now, nullable=False)

    tiger = relationship("Tiger", back_populates="sightings")
    camera = relationship("Camera", back_populates="sightings")
    embedding = relationship(
        "Embedding", back_populates="sighting", uselist=False,
        cascade="all, delete-orphan",
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id = Column(Integer, primary_key=True, index=True)

    tiger_id = Column(String, ForeignKey("tigers.tiger_id"), nullable=False)
    sighting_id = Column(
        String, ForeignKey("sightings.sighting_id"), unique=True, nullable=True
    )

    embedding_path = Column(String, nullable=False)  # relative path to .pt file
    dimension = Column(Integer, nullable=True)
    model_name = Column(String, nullable=True)  # e.g. "hf-hub:BVRA/MegaDescriptor-L-384"

    created_at = Column(DateTime, default=_now, nullable=False)

    tiger = relationship("Tiger", back_populates="embeddings")
    sighting = relationship("Sighting", back_populates="embedding")

    __table_args__ = (
        UniqueConstraint("sighting_id", name="uq_embedding_sighting"),
    )
