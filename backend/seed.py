"""
Optional seed script -- inserts a handful of example records so the API
and Swagger UI have something to look at. Does NOT insert fake images or
fake embeddings, only DB rows.

Usage (from the backend/ directory):

    python seed.py
"""

from datetime import datetime, timedelta, timezone

from app.database import SessionLocal, init_storage
from app import crud, schemas


def run():
    init_storage()
    db = SessionLocal()

    try:
        # Tigers
        for tiger_id, name in [("TIGER-001", "Raja"), ("TIGER-002", "Maya")]:
            if crud.get_tiger(db, tiger_id) is None:
                crud.create_tiger(
                    db, schemas.TigerCreate(tiger_id=tiger_id, name=name)
                )
                print(f"Created tiger: {tiger_id} ({name})")
            else:
                print(f"Tiger already exists, skipping: {tiger_id}")

        # Cameras
        for camera_id, name, lat, lon, loc in [
            ("CAM-001", "North Ridge Trail Cam", 21.1458, 79.0882, "North Ridge"),
            ("CAM-002", "River Bend Trail Cam", 21.1502, 79.0951, "River Bend"),
        ]:
            if crud.get_camera(db, camera_id) is None:
                crud.create_camera(
                    db,
                    schemas.CameraCreate(
                        camera_id=camera_id,
                        name=name,
                        latitude=lat,
                        longitude=lon,
                        location_name=loc,
                    ),
                )
                print(f"Created camera: {camera_id} ({name})")
            else:
                print(f"Camera already exists, skipping: {camera_id}")

        # Sightings (metadata only -- no fake images/embeddings on disk)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        sample_sightings = [
            ("TIGER-001", "CAM-001", now - timedelta(days=2)),
            ("TIGER-001", "CAM-002", now - timedelta(days=1)),
            ("TIGER-002", "CAM-002", now),
        ]
        for tiger_id, camera_id, ts in sample_sightings:
            crud.create_sighting(
                db,
                schemas.SightingCreate(
                    tiger_id=tiger_id,
                    camera_id=camera_id,
                    timestamp=ts,
                    confidence=0.95,
                ),
            )
        print(f"Created {len(sample_sightings)} sample sightings.")

        print("\nSeed complete.")

    finally:
        db.close()


if __name__ == "__main__":
    run()
