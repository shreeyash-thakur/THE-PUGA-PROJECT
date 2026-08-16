from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/sightings", tags=["sightings"])


@router.get("", response_model=list[schemas.SightingOut])
def list_sightings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_sightings(db, skip=skip, limit=limit)


@router.get("/{sighting_id}", response_model=schemas.SightingOut)
def get_sighting(sighting_id: str, db: Session = Depends(get_db)):
    sighting = crud.get_sighting(db, sighting_id)
    if sighting is None:
        raise HTTPException(
            status_code=404, detail=f"Sighting '{sighting_id}' not found"
        )
    return sighting


@router.post("", response_model=schemas.SightingOut, status_code=201)
def create_sighting(sighting: schemas.SightingCreate, db: Session = Depends(get_db)):
    if crud.get_tiger(db, sighting.tiger_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tiger '{sighting.tiger_id}' does not exist; create it first",
        )
    if sighting.camera_id is not None and crud.get_camera(db, sighting.camera_id) is None:
        raise HTTPException(
            status_code=404,
            detail=f"Camera '{sighting.camera_id}' does not exist; create it first",
        )
    return crud.create_sighting(db, sighting)
