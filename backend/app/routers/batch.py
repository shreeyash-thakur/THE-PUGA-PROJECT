"""HTTP layer for offline batch ingestion + quarantine management.

Business logic lives in app.services.batch_service and app.crud; this
module only maps HTTP errors to the right status codes.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import get_raw_images_dir
from app.database import get_db
from app.services import batch_service
from app.services.ai_pipeline import AIModelUnavailableError

router = APIRouter(prefix="/api/batch", tags=["batch"])


# ---------------------------------------------------------------------------
# RESTORE (declared BEFORE the {batch_id} GET route so "quarantine" never
# matches the dynamic segment)
# ---------------------------------------------------------------------------

@router.post(
    "/quarantine/{image_row_id}/restore",
    response_model=schemas.RestoreResponse,
)
def restore_quarantined_image(image_row_id: int, db: Session = Depends(get_db)):
    """Restore a quarantined image to its recorded original location.
    Returns 409 if the destination already exists (never overwrites)."""
    try:
        return batch_service.restore_quarantined(db, image_row_id)
    except batch_service.RestoreNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except batch_service.RestoreConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# Quarantine listing
# ---------------------------------------------------------------------------

@router.get("/quarantine", response_model=list[schemas.QuarantineItemOut])
def list_quarantined(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """List quarantined images (blank frames) across all batches, most
    recent first."""
    rows = crud.list_quarantined_images(db, skip=skip, limit=limit)
    return rows


# ---------------------------------------------------------------------------
# Batch ingestion + retrieval
# ---------------------------------------------------------------------------

@router.post("/analyze", response_model=schemas.BatchSummary, status_code=201)
def analyze_batch(
    request: schemas.BatchAnalyzeRequest = schemas.BatchAnalyzeRequest(),
    db: Session = Depends(get_db),
):
    """Ingest a raw camera-trap folder (default: the configured
    PUGA_RAW_IMAGES_DIR / D:\\penchimages) end to end: scan -> dedupe ->
    quarantine blanks -> run the existing /api/analyze pipeline on the
    rest. Runs synchronously; use `limit` to keep a demo run fast."""
    try:
        return batch_service.run_batch(db, request)
    except batch_service.FolderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AIModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[str])
def list_batches(db: Session = Depends(get_db)):
    """List all batch_ids that have been run so far, most recent first."""
    return crud.list_batch_ids(db)


@router.get("/config")
def get_batch_config():
    """The folder that will be scanned when `folder` is omitted from a
    POST /api/batch/analyze request."""
    return {"raw_images_dir": get_raw_images_dir()}


@router.get("/{batch_id}", response_model=schemas.BatchSummary)
def get_batch(batch_id: str, db: Session = Depends(get_db)):
    rows = crud.get_batch_images(db, batch_id)
    if not rows:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")
    return batch_service.build_batch_summary(db, batch_id, folder="")
