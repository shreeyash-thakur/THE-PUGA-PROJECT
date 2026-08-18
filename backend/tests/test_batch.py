"""
Tests for POST /api/batch/analyze and the quarantine/restore workflow.

As in test_analyze.py, the AI models are mocked (app.services.ai_pipeline)
so these tests don't need real weights/GPU. What's under test here is the
batch orchestration itself: folder scanning, hashing/dedupe, quarantining
blanks (reversibly), routing animal detections through the existing
analyze_service pipeline, and the quarantine listing/restore endpoints.

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


def _make_test_jpeg_bytes(color=(120, 60, 20)) -> bytes:
    img = Image.new("RGB", (120, 120), color=color)
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

    # A source folder to stand in for D:\penchimages in tests.
    raw_dir = os.path.join(tmp_dir, "raw_images")
    os.makedirs(raw_dir, exist_ok=True)

    with TestClient(main_module.app) as test_client:
        yield test_client, raw_dir

    main_module.app.dependency_overrides.clear()


@pytest.fixture()
def mock_animal_detection(monkeypatch):
    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )
    monkeypatch.setattr(
        ai_pipeline,
        "compute_embedding",
        lambda crop_image: torch.nn.functional.normalize(torch.rand(1, 1536), dim=1),
    )


@pytest.fixture()
def mock_no_animal_detection(monkeypatch):
    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_NO_ANIMAL
    )


def _write(raw_dir: str, name: str, color=(120, 60, 20)) -> str:
    path = os.path.join(raw_dir, name)
    with open(path, "wb") as f:
        f.write(_make_test_jpeg_bytes(color))
    return path


def test_batch_config_shows_default_folder(client):
    test_client, _ = client
    resp = test_client.get("/api/batch/config")
    assert resp.status_code == 200
    assert resp.json()["raw_images_dir"] == "D:\\penchimages"


def test_batch_analyze_missing_folder_404s(client):
    test_client, _ = client
    resp = test_client.post(
        "/api/batch/analyze", json={"folder": "/nonexistent/path/xyz"}
    )
    assert resp.status_code == 404


def test_batch_quarantines_blank_images(client, mock_no_animal_detection):
    test_client, raw_dir = client
    _write(raw_dir, "blank1.jpg", color=(10, 10, 10))
    _write(raw_dir, "blank2.jpg", color=(20, 20, 20))

    resp = test_client.post("/api/batch/analyze", json={"folder": raw_dir})
    assert resp.status_code == 201
    body = resp.json()

    assert body["total_files"] == 2
    assert body["quarantined"] == 2
    assert body["processed"] == 0
    assert body["failed"] == 0

    # Originals should be MOVED, not deleted -- gone from raw_dir...
    assert not os.path.exists(os.path.join(raw_dir, "blank1.jpg"))
    # ...and each row records where it went.
    for img in body["images"]:
        assert img["status"] == "quarantined"
        assert img["quarantine_path"] is not None
        assert img["reason"] == "no_animal_detected"

    # And the quarantine listing endpoint should show them.
    listing = test_client.get("/api/batch/quarantine").json()
    assert len(listing) == 2


def test_batch_routes_animal_images_through_analyze_pipeline(client, mock_animal_detection):
    test_client, raw_dir = client
    _write(raw_dir, "tiger1.jpg", color=(200, 100, 50))

    resp = test_client.post("/api/batch/analyze", json={"folder": raw_dir})
    assert resp.status_code == 201
    body = resp.json()

    assert body["total_files"] == 1
    # Empty gallery -> POSSIBLE_NEW -> needs_review (per reid_decision.py,
    # no sighting is auto-created).
    assert body["needs_review"] == 1
    assert body["quarantined"] == 0

    img = body["images"][0]
    assert img["status"] == "needs_review"
    assert img["match_status"] == "POSSIBLE_NEW"
    assert img["crop_path"] is not None

    # Original file untouched (it's not a blank).
    assert os.path.exists(os.path.join(raw_dir, "tiger1.jpg"))


def test_batch_deduplicates_identical_file_content(client, mock_no_animal_detection):
    test_client, raw_dir = client
    _write(raw_dir, "a.jpg", color=(50, 50, 50))
    _write(raw_dir, "a_copy.jpg", color=(50, 50, 50))  # identical bytes, different name

    resp = test_client.post("/api/batch/analyze", json={"folder": raw_dir})
    body = resp.json()

    assert body["total_files"] == 2
    statuses = sorted(img["status"] for img in body["images"])
    assert statuses == ["duplicate", "quarantined"]


def test_batch_resume_skips_already_terminal_files_on_rerun(client, mock_no_animal_detection):
    test_client, raw_dir = client
    _write(raw_dir, "blank.jpg", color=(30, 30, 30))

    first = test_client.post("/api/batch/analyze", json={"folder": raw_dir}).json()
    assert first["quarantined"] == 1

    # File was moved out of raw_dir into quarantine, so a second run over
    # the same folder should just see nothing left to process.
    second = test_client.post("/api/batch/analyze", json={"folder": raw_dir}).json()
    assert second["total_files"] == 0


def test_batch_bad_ai_dependency_marks_file_failed_not_whole_batch(client, monkeypatch):
    test_client, raw_dir = client
    _write(raw_dir, "broken.jpg")

    def _raise(*args, **kwargs):
        raise ai_pipeline.AIModelUnavailableError("weights not downloaded")

    monkeypatch.setattr(ai_pipeline, "run_detection", _raise)

    resp = test_client.post("/api/batch/analyze", json={"folder": raw_dir})
    assert resp.status_code == 201  # batch endpoint itself succeeds
    body = resp.json()
    assert body["failed"] == 1
    assert "weights not downloaded" in body["images"][0]["error"]


def test_list_batches_and_get_batch_by_id(client, mock_no_animal_detection):
    test_client, raw_dir = client
    _write(raw_dir, "x.jpg")

    created = test_client.post("/api/batch/analyze", json={"folder": raw_dir}).json()
    batch_id = created["batch_id"]

    listing = test_client.get("/api/batch").json()
    assert batch_id in listing

    detail = test_client.get(f"/api/batch/{batch_id}")
    assert detail.status_code == 200
    assert detail.json()["total_files"] == 1


def test_get_unknown_batch_404s(client):
    test_client, _ = client
    resp = test_client.get("/api/batch/BATCH-DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_restore_quarantined_image(client, mock_no_animal_detection):
    test_client, raw_dir = client
    original_path = _write(raw_dir, "restore_me.jpg", color=(60, 60, 60))

    created = test_client.post("/api/batch/analyze", json={"folder": raw_dir}).json()
    image_row_id = created["images"][0]["id"]

    assert not os.path.exists(original_path)  # moved to quarantine

    restore_resp = test_client.post(f"/api/batch/quarantine/{image_row_id}/restore")
    assert restore_resp.status_code == 200
    assert os.path.exists(original_path)  # back where it started

    # Should no longer show up in the quarantine listing.
    listing = test_client.get("/api/batch/quarantine").json()
    assert all(item["id"] != image_row_id for item in listing)


def test_restore_nonexistent_image_404s(client):
    test_client, _ = client
    resp = test_client.post("/api/batch/quarantine/99999/restore")
    assert resp.status_code == 404


def test_restore_conflict_when_destination_exists(client, mock_no_animal_detection):
    test_client, raw_dir = client
    original_path = _write(raw_dir, "conflict.jpg", color=(70, 70, 70))

    created = test_client.post("/api/batch/analyze", json={"folder": raw_dir}).json()
    image_row_id = created["images"][0]["id"]

    # Recreate a file at the original path before restoring.
    with open(original_path, "wb") as f:
        f.write(_make_test_jpeg_bytes())

    resp = test_client.post(f"/api/batch/quarantine/{image_row_id}/restore")
    assert resp.status_code == 409


def test_batch_limit_caps_files_processed(client, mock_no_animal_detection):
    test_client, raw_dir = client
    for i in range(5):
        _write(raw_dir, f"img{i}.jpg", color=(i * 10, i * 10, i * 10))

    resp = test_client.post(
        "/api/batch/analyze", json={"folder": raw_dir, "limit": 2}
    )
    body = resp.json()
    assert body["total_files"] == 2
