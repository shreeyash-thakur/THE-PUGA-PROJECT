"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# Tiger
# ---------------------------------------------------------------------------

class TigerBase(BaseModel):
    tiger_id: str
    name: Optional[str] = None
    status: str = "active"
    reference_image: Optional[str] = None


class TigerCreate(TigerBase):
    pass


class TigerUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None
    reference_image: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None


class TigerOut(TigerBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    total_sightings: int
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------

class CameraBase(BaseModel):
    camera_id: str
    name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None


class CameraCreate(CameraBase):
    pass


class CameraOut(CameraBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Sighting
# ---------------------------------------------------------------------------

class SightingBase(BaseModel):
    tiger_id: str
    camera_id: Optional[str] = None
    image_path: Optional[str] = None
    crop_path: Optional[str] = None
    embedding_path: Optional[str] = None
    similarity_score: Optional[float] = None
    confidence: Optional[float] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    timestamp: Optional[datetime] = None


class SightingCreate(SightingBase):
    pass


class SightingOut(SightingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sighting_id: str
    timestamp: datetime
    created_at: datetime


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

class EmbeddingBase(BaseModel):
    tiger_id: str
    sighting_id: Optional[str] = None
    embedding_path: str
    dimension: Optional[int] = None
    model_name: Optional[str] = None


class EmbeddingCreate(EmbeddingBase):
    pass


class EmbeddingOut(EmbeddingBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class Health(BaseModel):
    status: str
    database: str
    mode: str
