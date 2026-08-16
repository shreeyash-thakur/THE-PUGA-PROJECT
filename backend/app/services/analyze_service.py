"""
Orchestrates the full analyze pipeline:

    uploaded image
      -> save to backend/data/images/
      -> MegaDetector (app.services.ai_pipeline)
      -> crop best animal detection -> backend/data/crops/
      -> MegaDescriptor-L-384 embedding -> backend/data/embeddings/
      -> similarity vs. existing stored embeddings (informational only)
      -> Tiger / Sighting / Embedding rows (app.crud)

This module owns request validation and DB orchestration; all actual
model inference lives in app.services.ai_pipeline so the two concerns
stay separate, per the task's code-quality requirements.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import IMAGES_DIR, CROPS_DIR, EMBEDDINGS_DIR, DATA_DIR
from app.services import ai_pipeline

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
MAX_CANDIDATE_MATCHES = 5


class InvalidImageError(ValueError):
    """The uploaded file isn't a readable image / has a disallowed
    extension. Mapped to HTTP 400 by the router."""


class TigerNotFoundError(ValueError):
    """A caller-supplied tiger_id doesn't exist. Mapped to HTTP 404."""


def _validate_and_save_upload(upload: UploadFile, raw_bytes: bytes) -> tuple[str, Path]:
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise InvalidImageError(
            f"Unsupported file extension '{suffix}'. Allowed: "
            f"{sorted(ALLOWED_EXTENSIONS)}"
        )

    if not raw_bytes:
        raise InvalidImageError("Uploaded file is empty.")

    image_id = uuid.uuid4().hex[:12]
    safe_name = Path(upload.filename or "upload").name  # strip any path components
    dest_path = IMAGES_DIR / f"{image_id}_{safe_name}"

    dest_path.write_bytes(raw_bytes)

    # Confirm it's actually a decodable image, not just an allowed
    # extension -- PIL's verify() is cheap and catches truncated/corrupt
    # uploads early.
    try:
        with Image.open(dest_path) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        dest_path.unlink(missing_ok=True)
        raise InvalidImageError(f"File is not a valid image: {exc}") from exc

    return image_id, dest_path


def _relative(path: Path) -> str:
    """Store portable, forward-slash relative paths in the DB (relative
    to backend/data/), never absolute paths."""
    return path.resolve().relative_to(DATA_DIR.resolve()).as_posix()


def analyze_image(
    db: Session,
    upload: UploadFile,
    raw_bytes: bytes,
    tiger_id: Optional[str] = None,
    camera_id: Optional[str] = None,
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    location_name: Optional[str] = None,
    detection_threshold: float = 0.2,
) -> schemas.AnalyzeResponse:
    """Run the full pipeline for one uploaded image. Raises
    InvalidImageError / TigerNotFoundError for request problems, and lets
    ai_pipeline.AIModelUnavailableError bubble up for the router to turn
    into a 503."""

    if tiger_id is not None and crud.get_tiger(db, tiger_id) is None:
        raise TigerNotFoundError(f"Tiger '{tiger_id}' does not exist.")

    if camera_id is not None and crud.get_camera(db, camera_id) is None:
        raise TigerNotFoundError(f"Camera '{camera_id}' does not exist.")

    image_id, image_path = _validate_and_save_upload(upload, raw_bytes)
    image_rel_path = _relative(image_path)

    detections = ai_pipeline.run_detection(image_path, threshold=detection_threshold)
    best = ai_pipeline.select_best_animal_detection(detections)

    if best is None:
        return schemas.AnalyzeResponse(
            image_id=image_id,
            image_path=image_rel_path,
            detections=detections,
            animal_detected=False,
            note=(
                "No animal detected above the confidence threshold. "
                "Image was saved; no crop, embedding, or sighting was "
                "created."
            ),
        )

    # --- crop -------------------------------------------------------
    with Image.open(image_path) as full_image:
        crop = ai_pipeline.crop_detection(full_image.convert("RGB"), best["bbox"])
        crop_path = CROPS_DIR / f"{image_id}_crop.jpg"
        crop.save(crop_path, quality=95)
    crop_rel_path = _relative(crop_path)

    # --- embedding ----------------------------------------------------
    embedding_tensor = ai_pipeline.compute_embedding(crop)
    embedding_path = EMBEDDINGS_DIR / f"{image_id}_embedding.pt"
    ai_pipeline.save_embedding(embedding_tensor, embedding_path)
    embedding_rel_path = _relative(embedding_path)

    # --- similarity vs. existing gallery (informational only) --------
    #
    # IMPORTANT: this query runs *before* the new Tiger/Sighting/Embedding
    # rows are committed below, so the embedding we just computed cannot
    # already be in `existing_embeddings` via the DB. We additionally
    # guard by embedding_path (belt-and-suspenders) so that even if this
    # ordering is ever changed by a future edit, the new embedding can
    # never be compared against itself.
    candidate_matches: list[schemas.CandidateMatch] = []
    best_similarity: Optional[float] = None

    existing_embeddings = crud.get_all_embeddings(db)
    per_tiger_best: dict[str, float] = {}
    for existing in existing_embeddings:
        if existing.embedding_path == embedding_rel_path:
            # Defensive guard against self-comparison -- see note above.
            continue

        existing_path = Path(existing.embedding_path)
        if not existing_path.is_absolute():
            existing_path = DATA_DIR / existing_path
        try:
            other_tensor = ai_pipeline.load_embedding(existing_path)
        except FileNotFoundError:
            continue  # stale DB row pointing at a missing file; skip it

        score = ai_pipeline.cosine_similarity(embedding_tensor, other_tensor)
        if existing.tiger_id not in per_tiger_best or score > per_tiger_best[existing.tiger_id]:
            per_tiger_best[existing.tiger_id] = score

    ranked = sorted(per_tiger_best.items(), key=lambda kv: kv[1], reverse=True)
    for other_tiger_id, score in ranked[:MAX_CANDIDATE_MATCHES]:
        candidate_matches.append(
            schemas.CandidateMatch(tiger_id=other_tiger_id, similarity_score=score)
        )
    if ranked:
        best_similarity = ranked[0][1]

    # --- tiger record --------------------------------------------------
    if tiger_id is not None:
        resolved_tiger_id = tiger_id
        tiger_status = "matched"  # explicitly assigned by the caller
    else:
        resolved_tiger_id = crud.generate_unique_tiger_id(db)
        crud.create_tiger(
            db,
            schemas.TigerCreate(
                tiger_id=resolved_tiger_id,
                status="unidentified",
            ),
        )
        tiger_status = "new"

    # --- sighting + embedding rows --------------------------------------
    sighting = crud.create_sighting(
        db,
        schemas.SightingCreate(
            tiger_id=resolved_tiger_id,
            camera_id=camera_id,
            image_path=image_rel_path,
            crop_path=crop_rel_path,
            embedding_path=embedding_rel_path,
            similarity_score=best_similarity,
            confidence=best["confidence"],
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
        ),
    )

    embedding_row = crud.create_embedding(
        db,
        schemas.EmbeddingCreate(
            tiger_id=resolved_tiger_id,
            sighting_id=sighting.sighting_id,
            embedding_path=embedding_rel_path,
            dimension=embedding_tensor.shape[-1],
            model_name=ai_pipeline.MEGADESCRIPTOR_MODEL_NAME,
        ),
    )

    note = (
        "Similarity scores are informational only -- no fixed threshold "
        "is applied, so 'candidate_matches' is not an automatic "
        "identification. "
    )
    note += (
        f"Sighting assigned to caller-specified tiger '{resolved_tiger_id}'."
        if tiger_status == "matched"
        else f"No tiger_id was supplied, so a new tiger '{resolved_tiger_id}' "
        "was created; review candidate_matches to decide whether this is "
        "actually a known tiger."
    )

    return schemas.AnalyzeResponse(
        image_id=image_id,
        image_path=image_rel_path,
        detections=detections,
        animal_detected=True,
        used_detection=best,
        crop_path=crop_rel_path,
        embedding_id=embedding_row.id,
        embedding_path=embedding_rel_path,
        sighting_id=sighting.sighting_id,
        tiger_id=resolved_tiger_id,
        tiger_status=tiger_status,
        candidate_matches=candidate_matches,
        note=note,
    )


def get_analysis_result(db: Session, sighting_id: str) -> Optional[schemas.AnalyzeResultOut]:
    sighting = crud.get_sighting(db, sighting_id)
    if sighting is None:
        return None

    tiger = crud.get_tiger(db, sighting.tiger_id)
    embedding = crud.get_embedding_for_sighting(db, sighting_id)

    return schemas.AnalyzeResultOut(
        sighting=sighting,
        tiger=tiger,
        embedding=embedding,
    )
