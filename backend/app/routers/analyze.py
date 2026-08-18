from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services import analyze_service
from app.services.ai_pipeline import AIModelUnavailableError

router = APIRouter(prefix="/api/analyze", tags=["analyze"])


@router.post("", response_model=schemas.AnalyzeResponse, status_code=201)
async def analyze_image(
    file: UploadFile = File(..., description="Camera-trap image to analyze"),
    tiger_id: str | None = Form(
        None, description="Assign this sighting to an existing tiger_id instead of creating a new one"
    ),
    camera_id: str | None = Form(None),
    latitude: float | None = Form(None),
    longitude: float | None = Form(None),
    location_name: str | None = Form(None),
    detection_threshold: float = Form(0.2),
    db: Session = Depends(get_db),
):
    """Run the full MegaDetector -> crop -> MegaDescriptor -> SQLite
    pipeline on one uploaded image.

    If `tiger_id` is supplied, the sighting is assigned to that tiger
    directly (explicit human decision).

    Otherwise, the Re-ID decision engine (app.services.reid_decision)
    classifies the best similarity match against the existing gallery as
    AUTO_MATCH, REVIEW, or POSSIBLE_NEW:
      - AUTO_MATCH: the sighting is automatically assigned to the
        matched existing tiger.
      - REVIEW / POSSIBLE_NEW: no tiger is created or assigned
        automatically; `match_status`/`review_required` tell the caller
        a human needs to decide. No Sighting/Embedding row is created
        for this case yet -- that's handled by the human-review workflow.
    """
    raw_bytes = await file.read()

    try:
        return analyze_service.analyze_image(
            db=db,
            upload=file,
            raw_bytes=raw_bytes,
            tiger_id=tiger_id,
            camera_id=camera_id,
            latitude=latitude,
            longitude=longitude,
            location_name=location_name,
            detection_threshold=detection_threshold,
        )
    except analyze_service.InvalidImageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except analyze_service.TigerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AIModelUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/{sighting_id}", response_model=schemas.AnalyzeResultOut)
def get_analysis_result(sighting_id: str, db: Session = Depends(get_db)):
    """Retrieve the sighting + tiger + embedding produced by a previous
    /api/analyze call."""
    result = analyze_service.get_analysis_result(db, sighting_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"Sighting '{sighting_id}' not found"
        )
    return result
