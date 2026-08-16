"""
Tests for the /api/analyze integration.

The AI models (MegaDetector, MegaDescriptor) are heavy, GPU-oriented, and
need weights downloaded from the internet -- not something a test suite
should require on every run. So these tests monkeypatch
app.services.ai_pipeline's detection/embedding functions with small fakes
and verify the orchestration logic around them: file saving, DB record
creation, tiger auto-creation vs. explicit assignment, similarity
scoring, and error handling.

Run from backend/:  pytest -q
"""

import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import torch
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import main as main_module
from app.services import ai_pipeline


FAKE_DETECTION_WITH_ANIMAL = [
    {"category": "animal", "confidence": 0.87, "bbox": [10.0, 10.0, 90.0, 90.0]}
]
FAKE_DETECTION_NO_ANIMAL = [
    {"category": "person", "confidence": 0.75, "bbox": [0.0, 0.0, 50.0, 50.0]}
]


def _make_test_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (120, 120), color=(120, 60, 20))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch):
    tmp_dir = tempfile.mkdtemp()
    tmp_db_path = os.path.join(tmp_dir, "test_puga.db")

    engine = create_engine(
        f"sqlite:///{tmp_db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db

    # Redirect data directories to a temp folder so tests never touch the
    # real backend/data/.
    from app import database as db_module
    from app.services import analyze_service

    tmp_data_dir = os.path.join(tmp_dir, "data")
    images_dir = os.path.join(tmp_data_dir, "images")
    crops_dir = os.path.join(tmp_data_dir, "crops")
    embeddings_dir = os.path.join(tmp_data_dir, "embeddings")
    for d in (images_dir, crops_dir, embeddings_dir):
        os.makedirs(d, exist_ok=True)

    from pathlib import Path

    monkeypatch.setattr(db_module, "DATA_DIR", Path(tmp_data_dir))
    monkeypatch.setattr(db_module, "IMAGES_DIR", Path(images_dir))
    monkeypatch.setattr(db_module, "CROPS_DIR", Path(crops_dir))
    monkeypatch.setattr(db_module, "EMBEDDINGS_DIR", Path(embeddings_dir))
    monkeypatch.setattr(analyze_service, "IMAGES_DIR", Path(images_dir))
    monkeypatch.setattr(analyze_service, "CROPS_DIR", Path(crops_dir))
    monkeypatch.setattr(analyze_service, "EMBEDDINGS_DIR", Path(embeddings_dir))
    monkeypatch.setattr(analyze_service, "DATA_DIR", Path(tmp_data_dir))

    with TestClient(main_module.app) as test_client:
        yield test_client

    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def mock_detection_with_animal(monkeypatch):
    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )
    monkeypatch.setattr(
        ai_pipeline,
        "compute_embedding",
        lambda crop_image: torch.nn.functional.normalize(torch.rand(1, 1536), dim=1),
    )


@pytest.fixture()
def mock_detection_no_animal(monkeypatch):
    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_NO_ANIMAL
    )


def test_analyze_creates_new_tiger_when_animal_found(client, mock_detection_with_animal):
    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)

    assert resp.status_code == 201
    body = resp.json()

    assert body["animal_detected"] is True
    assert body["tiger_status"] == "new"
    assert body["tiger_id"].startswith("TIGER-")
    assert body["sighting_id"] is not None
    assert body["embedding_id"] is not None
    assert body["crop_path"] is not None
    assert body["candidate_matches"] == []  # nothing in the gallery yet

    # The tiger and sighting should be independently retrievable.
    tiger_resp = client.get(f"/api/tigers/{body['tiger_id']}")
    assert tiger_resp.status_code == 200
    assert tiger_resp.json()["status"] == "unidentified"

    sighting_resp = client.get(f"/api/sightings/{body['sighting_id']}")
    assert sighting_resp.status_code == 200


def test_analyze_no_animal_creates_no_records(client, mock_detection_no_animal):
    files = {"file": ("empty.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)

    assert resp.status_code == 201
    body = resp.json()

    assert body["animal_detected"] is False
    assert body["sighting_id"] is None
    assert body["tiger_id"] is None
    assert body["detections"] == FAKE_DETECTION_NO_ANIMAL


def test_analyze_with_explicit_tiger_id(client, mock_detection_with_animal):
    client.post("/api/tigers", json={"tiger_id": "TIGER-KNOWN", "name": "Raja"})

    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post(
        "/api/analyze", files=files, data={"tiger_id": "TIGER-KNOWN"}
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["tiger_id"] == "TIGER-KNOWN"
    assert body["tiger_status"] == "matched"


def test_analyze_with_nonexistent_tiger_id_404s(client, mock_detection_with_animal):
    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post(
        "/api/analyze", files=files, data={"tiger_id": "TIGER-NOPE"}
    )
    assert resp.status_code == 404


def test_analyze_rejects_non_image_file(client, mock_detection_with_animal):
    files = {"file": ("notes.txt", b"hello world", "text/plain")}
    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 400


def test_analyze_similarity_scoring_against_existing_gallery(client, monkeypatch):
    """Two analyze calls with a fixed embedding should see each other in
    candidate_matches with similarity 1.0 (identical fake embedding)."""
    fixed_embedding = torch.nn.functional.normalize(torch.ones(1, 1536), dim=1)

    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )
    monkeypatch.setattr(
        ai_pipeline, "compute_embedding", lambda crop_image: fixed_embedding.clone()
    )

    files = {"file": ("tiger1.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    first = client.post("/api/analyze", files=files).json()

    files = {"file": ("tiger2.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    second = client.post("/api/analyze", files=files).json()

    assert second["candidate_matches"], "expected at least one candidate match"
    match = second["candidate_matches"][0]
    assert match["tiger_id"] == first["tiger_id"]
    assert match["similarity_score"] == pytest.approx(1.0, abs=1e-3)


def test_get_analysis_result(client, mock_detection_with_animal):
    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    created = client.post("/api/analyze", files=files).json()

    resp = client.get(f"/api/analyze/{created['sighting_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sighting"]["sighting_id"] == created["sighting_id"]
    assert body["tiger"]["tiger_id"] == created["tiger_id"]
    assert body["embedding"]["id"] == created["embedding_id"]


def test_get_analysis_result_404_for_unknown_sighting(client):
    resp = client.get("/api/analyze/SGT-DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_ai_model_unavailable_returns_503(client, monkeypatch):
    def _raise(*args, **kwargs):
        raise ai_pipeline.AIModelUnavailableError("weights not downloaded")

    monkeypatch.setattr(ai_pipeline, "run_detection", _raise)

    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 503
