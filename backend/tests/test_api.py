"""
Basic automated test suite for the PUGA offline backend.

Runs against a temporary SQLite file (not backend/database/puga.db), so it
never touches real data. Run from the backend/ directory:

    pytest -q
"""

import os
import sys
import tempfile

# Make sure `app` is importable when running `pytest` from backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app import main as main_module


@pytest.fixture()
def client():
    tmp_dir = tempfile.mkdtemp()
    tmp_db_path = os.path.join(tmp_dir, "test_puga.db")

    engine = create_engine(
        f"sqlite:///{tmp_db_path}", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app import models  # noqa: F401 -- register models on Base.metadata

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db

    with TestClient(main_module.app) as test_client:
        yield test_client

    main_module.app.dependency_overrides.clear()


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["mode"] == "offline"


def test_create_and_get_tiger(client):
    resp = client.post("/api/tigers", json={"tiger_id": "TIGER-001", "name": "Raja"})
    assert resp.status_code == 201
    assert resp.json()["tiger_id"] == "TIGER-001"

    resp = client.get("/api/tigers/TIGER-001")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Raja"


def test_duplicate_tiger_rejected(client):
    client.post("/api/tigers", json={"tiger_id": "TIGER-002"})
    resp = client.post("/api/tigers", json={"tiger_id": "TIGER-002"})
    assert resp.status_code == 409


def test_missing_tiger_404(client):
    resp = client.get("/api/tigers/TIGER-DOES-NOT-EXIST")
    assert resp.status_code == 404


def test_create_camera(client):
    resp = client.post(
        "/api/cameras",
        json={"camera_id": "CAM-001", "name": "North Ridge", "latitude": 21.1, "longitude": 79.0},
    )
    assert resp.status_code == 201
    assert resp.json()["camera_id"] == "CAM-001"


def test_create_sighting_and_tiger_rollup(client):
    client.post("/api/tigers", json={"tiger_id": "TIGER-003"})
    client.post("/api/cameras", json={"camera_id": "CAM-002", "name": "River Bend"})

    resp = client.post(
        "/api/sightings",
        json={"tiger_id": "TIGER-003", "camera_id": "CAM-002", "confidence": 0.9},
    )
    assert resp.status_code == 201
    sighting = resp.json()
    assert sighting["tiger_id"] == "TIGER-003"
    assert "sighting_id" in sighting

    # total_sightings on the parent tiger should now be 1
    tiger = client.get("/api/tigers/TIGER-003").json()
    assert tiger["total_sightings"] == 1


def test_sighting_requires_existing_tiger(client):
    resp = client.post("/api/sightings", json={"tiger_id": "NO-SUCH-TIGER"})
    assert resp.status_code == 404


def test_list_sightings_for_tiger(client):
    client.post("/api/tigers", json={"tiger_id": "TIGER-004"})
    client.post("/api/sightings", json={"tiger_id": "TIGER-004"})
    client.post("/api/sightings", json={"tiger_id": "TIGER-004"})

    resp = client.get("/api/tigers/TIGER-004/sightings")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_swagger_docs_available(client):
    resp = client.get("/docs")
    assert resp.status_code == 200
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
