from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud, schemas
from app.database import get_db

router = APIRouter(prefix="/api/tigers", tags=["tigers"])


@router.get("", response_model=list[schemas.TigerOut])
def list_tigers(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_tigers(db, skip=skip, limit=limit)


@router.get("/{tiger_id}", response_model=schemas.TigerOut)
def get_tiger(tiger_id: str, db: Session = Depends(get_db)):
    tiger = crud.get_tiger(db, tiger_id)
    if tiger is None:
        raise HTTPException(status_code=404, detail=f"Tiger '{tiger_id}' not found")
    return tiger


@router.post("", response_model=schemas.TigerOut, status_code=201)
def create_tiger(tiger: schemas.TigerCreate, db: Session = Depends(get_db)):
    if crud.get_tiger(db, tiger.tiger_id) is not None:
        raise HTTPException(
            status_code=409, detail=f"Tiger '{tiger.tiger_id}' already exists"
        )
    return crud.create_tiger(db, tiger)


@router.put("/{tiger_id}", response_model=schemas.TigerOut)
def update_tiger(
    tiger_id: str, update: schemas.TigerUpdate, db: Session = Depends(get_db)
):
    tiger = crud.update_tiger(db, tiger_id, update)
    if tiger is None:
        raise HTTPException(status_code=404, detail=f"Tiger '{tiger_id}' not found")
    return tiger


@router.delete("/{tiger_id}", status_code=204)
def delete_tiger(tiger_id: str, db: Session = Depends(get_db)):
    deleted = crud.delete_tiger(db, tiger_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Tiger '{tiger_id}' not found")
    return None


@router.get("/{tiger_id}/sightings", response_model=list[schemas.SightingOut])
def get_tiger_sightings(
    tiger_id: str, skip: int = 0, limit: int = 100, db: Session = Depends(get_db)
):
    if crud.get_tiger(db, tiger_id) is None:
        raise HTTPException(status_code=404, detail=f"Tiger '{tiger_id}' not found")
    return crud.get_sightings_for_tiger(db, tiger_id, skip=skip, limit=limit)
