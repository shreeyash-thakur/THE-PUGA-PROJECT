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
    """With an empty gallery, best_similarity is None -> POSSIBLE_NEW.
    Per the Re-ID decision engine spec, no tiger is auto-created and no
    sighting is persisted for POSSIBLE_NEW; the caller gets the decision
    plus the saved image/crop for a future human-review step."""
    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)

    assert resp.status_code == 201
    body = resp.json()

    assert body["animal_detected"] is True
    assert body["match_status"] == "POSSIBLE_NEW"
    assert body["review_required"] is True
    assert body["matched_tiger_id"] is None
    assert body["tiger_status"] is None
    assert body["tiger_id"] is None
    assert body["sighting_id"] is None
    assert body["embedding_id"] is None
    assert body["crop_path"] is not None
    assert body["candidate_matches"] == []  # nothing in the gallery yet


def test_analyze_no_animal_creates_no_records(client, mock_detection_no_animal):
    files = {"file": ("empty.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)

    assert resp.status_code == 201
    body = resp.json()

    assert body["animal_detected"] is False
    assert body["sighting_id"] is None
    assert body["tiger_id"] is None
    assert body["match_status"] is None
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


def test_analyze_similarity_scoring_and_auto_match(client, monkeypatch):
    """Seed a known tiger via an explicit-tiger_id analyze call (so its
    embedding is actually persisted), then a second, automatic call with
    an identical embedding should score similarity 1.0 against it and
    the Re-ID decision engine should AUTO_MATCH it to that tiger."""
    fixed_embedding = torch.nn.functional.normalize(torch.ones(1, 1536), dim=1)

    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )
    monkeypatch.setattr(
        ai_pipeline, "compute_embedding", lambda crop_image: fixed_embedding.clone()
    )

    client.post("/api/tigers", json={"tiger_id": "TIGER-SEED", "name": "Seed"})
    files = {"file": ("tiger1.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    first = client.post(
        "/api/analyze", files=files, data={"tiger_id": "TIGER-SEED"}
    ).json()
    assert first["tiger_status"] == "matched"

    files = {"file": ("tiger2.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    second = client.post("/api/analyze", files=files).json()

    assert second["candidate_matches"], "expected at least one candidate match"
    match = second["candidate_matches"][0]
    assert match["tiger_id"] == "TIGER-SEED"
    assert match["similarity_score"] == pytest.approx(1.0, abs=1e-3)

    assert second["match_status"] == "AUTO_MATCH"
    assert second["matched_tiger_id"] == "TIGER-SEED"
    assert second["tiger_id"] == "TIGER-SEED"
    assert second["tiger_status"] == "matched"
    assert second["review_required"] is False
    assert second["sighting_id"] is not None
    assert second["embedding_id"] is not None


def test_analyze_review_status_for_middle_similarity(client, monkeypatch):
    """A best similarity strictly between REID_REVIEW_THRESHOLD and
    REID_AUTO_MATCH_THRESHOLD must produce REVIEW, and REVIEW must NOT
    assign or create any tiger (task requirement #8)."""
    embedding_a = torch.zeros(1, 1536)
    embedding_a[0, 0] = 1.0

    # cosine_similarity(a, b) == 0.6 exactly -- between the default
    # REVIEW_THRESHOLD (0.50) and AUTO_MATCH_THRESHOLD (0.75).
    embedding_b = torch.zeros(1, 1536)
    embedding_b[0, 0] = 0.6
    embedding_b[0, 1] = 0.8

    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )

    client.post("/api/tigers", json={"tiger_id": "TIGER-REVIEW-BASE"})
    monkeypatch.setattr(ai_pipeline, "compute_embedding", lambda crop_image: embedding_a.clone())
    files = {"file": ("base.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    client.post("/api/analyze", files=files, data={"tiger_id": "TIGER-REVIEW-BASE"})

    monkeypatch.setattr(ai_pipeline, "compute_embedding", lambda crop_image: embedding_b.clone())
    files = {"file": ("candidate.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    resp = client.post("/api/analyze", files=files)
    assert resp.status_code == 201
    body = resp.json()

    assert body["candidate_matches"][0]["similarity_score"] == pytest.approx(0.6, abs=1e-3)
    assert body["match_status"] == "REVIEW"
    assert body["review_required"] is True
    assert body["matched_tiger_id"] is None
    assert body["tiger_id"] is None
    assert body["tiger_status"] is None
    assert body["sighting_id"] is None
    assert body["embedding_id"] is None

    # No new tiger was created, and the base tiger's rollup is untouched.
    base = client.get("/api/tigers/TIGER-REVIEW-BASE").json()
    assert base["total_sightings"] == 1


class _FakeUpload:
    """Minimal stand-in for FastAPI's UploadFile -- analyze_service only
    reads `.filename` off it."""

    def __init__(self, filename: str):
        self.filename = filename


@pytest.fixture()
def service_env(monkeypatch, tmp_path):
    """Lower-level fixture that gives direct access to a DB session and
    the (path-patched) analyze_service module, bypassing the HTTP layer.
    Used for white-box tests of the self-comparison guard that need to
    seed specific DB rows / files that aren't reachable through the
    public API."""
    from app import models  # noqa: F401
    from app.database import Base
    from app.services import analyze_service as service_module

    db_path = tmp_path / "svc_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    data_dir = tmp_path / "data"
    images_dir = data_dir / "images"
    crops_dir = data_dir / "crops"
    embeddings_dir = data_dir / "embeddings"
    for d in (images_dir, crops_dir, embeddings_dir):
        d.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(service_module, "DATA_DIR", data_dir)
    monkeypatch.setattr(service_module, "IMAGES_DIR", images_dir)
    monkeypatch.setattr(service_module, "CROPS_DIR", crops_dir)
    monkeypatch.setattr(service_module, "EMBEDDINGS_DIR", embeddings_dir)

    db = TestingSessionLocal()
    try:
        yield db, service_module
    finally:
        db.close()


def test_first_analyze_call_never_matches_itself(client, mock_detection_with_animal):
    """Regression test for the audited '1.0 similarity' report: with an
    empty gallery, a brand-new sighting's own embedding must never appear
    in its own candidate_matches (and, per the Re-ID decision engine,
    an empty gallery -> POSSIBLE_NEW, so no tiger is assigned either)."""
    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    body = client.post("/api/analyze", files=files).json()

    assert body["candidate_matches"] == []
    assert body["match_status"] == "POSSIBLE_NEW"
    assert body["tiger_id"] is None
    assert body["tiger_id"] not in [m["tiger_id"] for m in body["candidate_matches"]]


def test_distinct_embeddings_do_not_score_as_identical(client, monkeypatch):
    """Sanity check for the opposite failure mode: two genuinely
    different embeddings must NOT be reported as a perfect match, proving
    the comparison logic still discriminates correctly (not just always
    returning 1.0). Similarity 0.0 is well below REID_REVIEW_THRESHOLD,
    so this should also decide POSSIBLE_NEW and not assign tiger A."""
    embedding_a = torch.zeros(1, 1536)
    embedding_a[0, 0] = 1.0  # unit vector along axis 0

    embedding_b = torch.zeros(1, 1536)
    embedding_b[0, 1] = 1.0  # unit vector along axis 1 -- orthogonal to A

    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )

    client.post("/api/tigers", json={"tiger_id": "TIGER-A"})
    monkeypatch.setattr(ai_pipeline, "compute_embedding", lambda crop_image: embedding_a.clone())
    files = {"file": ("tiger_a.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    client.post("/api/analyze", files=files, data={"tiger_id": "TIGER-A"})

    monkeypatch.setattr(ai_pipeline, "compute_embedding", lambda crop_image: embedding_b.clone())
    files = {"file": ("tiger_b.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    second = client.post("/api/analyze", files=files).json()

    assert second["candidate_matches"], "expected a candidate match against tiger A"
    assert second["candidate_matches"][0]["similarity_score"] == pytest.approx(0.0, abs=1e-3)
    assert second["match_status"] == "POSSIBLE_NEW"
    assert second["tiger_id"] is None


def test_guard_excludes_embedding_path_collision(service_env, monkeypatch):
    """White-box regression test for the exact self-comparison scenario
    the audit was checking for: if a DB row's embedding_path ever ends up
    identical to the embedding_path about to be used for the *current*
    request (e.g. a future refactor that saves/commits the new embedding
    before running the gallery comparison), the guard in
    analyze_service.analyze_image must exclude that row rather than
    silently comparing the new embedding to itself.

    We force this collision deterministically by pinning
    `_validate_and_save_upload`'s image_id for two consecutive calls, so
    both calls compute the exact same embedding_path. Without the
    `existing.embedding_path == embedding_rel_path` guard, this test
    fails (the decoy tiger would show up in candidate_matches at 1.0,
    because by the time it's compared its file has literally been
    overwritten with the new call's embedding).

    The decoy call uses an explicit tiger_id so its embedding is actually
    persisted -- the Re-ID decision engine's automatic path (no
    tiger_id) does not persist an embedding for REVIEW/POSSIBLE_NEW, so
    it wouldn't otherwise be in the gallery for the collision to bite."""
    db, service_module = service_env

    fixed_embedding = torch.nn.functional.normalize(torch.full((1, 1536), 2.0), dim=1)
    monkeypatch.setattr(
        ai_pipeline, "run_detection", lambda path, threshold=0.2: FAKE_DETECTION_WITH_ANIMAL
    )
    monkeypatch.setattr(ai_pipeline, "compute_embedding", lambda crop_image: fixed_embedding.clone())

    fixed_image_id = "collide1234x"
    original_validate = service_module._validate_and_save_upload

    def forced_validate(upload, raw_bytes):
        _, path = original_validate(upload, raw_bytes)
        return fixed_image_id, path

    monkeypatch.setattr(service_module, "_validate_and_save_upload", forced_validate)

    from app import crud, schemas as app_schemas

    crud.create_tiger(db, app_schemas.TigerCreate(tiger_id="TIGER-DECOY", status="active"))
    decoy_result = service_module.analyze_image(
        db=db,
        upload=_FakeUpload("decoy.jpg"),
        raw_bytes=_make_test_jpeg_bytes(),
        tiger_id="TIGER-DECOY",
    )
    assert decoy_result.tiger_status == "matched"
    decoy_tiger_id = decoy_result.tiger_id

    # Second call reuses the identical forced image_id, so its
    # embedding_path collides exactly with the decoy's DB row.
    second_result = service_module.analyze_image(
        db=db, upload=_FakeUpload("real.jpg"), raw_bytes=_make_test_jpeg_bytes()
    )

    matched_tiger_ids = [m.tiger_id for m in second_result.candidate_matches]
    assert decoy_tiger_id not in matched_tiger_ids, (
        "the path-collision guard should have excluded this row instead "
        "of comparing the new embedding to itself"
    )
    # With the (correctly excluded) decoy as the only possible candidate,
    # the gallery is effectively empty -> POSSIBLE_NEW.
    assert second_result.match_status == "POSSIBLE_NEW"


def test_get_analysis_result(client, mock_detection_with_animal):
    client.post("/api/tigers", json={"tiger_id": "TIGER-GETRESULT"})
    files = {"file": ("tiger.jpg", _make_test_jpeg_bytes(), "image/jpeg")}
    created = client.post(
        "/api/analyze", files=files, data={"tiger_id": "TIGER-GETRESULT"}
    ).json()

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
