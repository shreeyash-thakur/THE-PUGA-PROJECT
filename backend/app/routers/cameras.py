from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[schemas.CameraOut])
def list_cameras(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_cameras(db, skip=skip, limit=limit)


@router.post("", response_model=schemas.CameraOut, status_code=201)
def create_camera(camera: schemas.CameraCreate, db: Session = Depends(get_db)):
    if crud.get_camera(db, camera.camera_id) is not None:
        raise HTTPException(
            status_code=409, detail=f"Camera '{camera.camera_id}' already exists"
        )
    return crud.create_camera(db, camera)
