"""
Batch ingestion for a raw camera-trap folder (e.g. D:\\penchimages).

    folder of raw images
      -> scan (recursive, dedupe by content hash)
      -> for each new file: reuse app.services.analyze_service.analyze_image
           - no animal detected -> move original to data/quarantine/{batch_id}/
                                    (reversible; nothing is ever deleted)
           - animal detected    -> AUTO_MATCH / REVIEW / POSSIBLE_NEW, exactly
                                    as a single POST /api/analyze call would
      -> BatchImage row per file (app.crud) records the outcome for audit
         + resumability

This module deliberately does NOT reimplement any detection/embedding/
matching logic -- it only orchestrates calling analyze_service per file,
which is the same code path POST /api/analyze already uses and already
has test coverage for.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import get_raw_images_dir
from app.services import analyze_service
from app.services.ai_pipeline import AIModelUnavailableError

IMAGE_EXTENSIONS = analyze_service.ALLOWED_EXTENSIONS


def _quarantine_root() -> Path:
    """Computed on every call (not a frozen module-level constant) so it
    always reflects the current app.services.analyze_service.DATA_DIR --
    important for tests, which monkeypatch DATA_DIR per-test."""
    return analyze_service.DATA_DIR / "quarantine"


class FolderNotFoundError(ValueError):
    """The requested raw-images folder doesn't exist. Mapped to HTTP 404
    by the router."""


class RestoreNotFoundError(ValueError):
    """No quarantined BatchImage row with this id. Mapped to HTTP 404."""


class RestoreConflictError(ValueError):
    """A file already exists at the restore destination -- refuse to
    overwrite it. Mapped to HTTP 409."""


class _FakeUpload:
    """Minimal stand-in for FastAPI's UploadFile -- analyze_service only
    reads `.filename` off it, so a batch file read from disk can reuse
    the exact same analyze_image() code path as a real HTTP upload."""

    def __init__(self, filename: str):
        self.filename = filename


def new_batch_id() -> str:
    import uuid

    return f"BATCH-{uuid.uuid4().hex[:10].upper()}"


def resolve_folder(folder: Optional[str]) -> Path:
    raw = folder or get_raw_images_dir()
    path = Path(raw)
    if not path.exists() or not path.is_dir():
        raise FolderNotFoundError(
            f"Raw images folder not found: '{raw}'. Create it (or set "
            "PUGA_RAW_IMAGES_DIR / pass 'folder' in the request) before "
            "running a batch."
        )
    return path


def scan_images(folder: Path, recursive: bool = True) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        p
        for p in folder.glob(pattern)
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _quarantine_destination(batch_id: str, filename: str) -> Path:
    """Collision-safe destination under data/quarantine/{batch_id}/ --
    never overwrites an existing file."""
    batch_dir = _quarantine_root() / batch_id
    batch_dir.mkdir(parents=True, exist_ok=True)

    dest = batch_dir / filename
    if not dest.exists():
        return dest

    stem, suffix = Path(filename).stem, Path(filename).suffix
    n = 1
    while True:
        candidate = batch_dir / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


def _relative_to_data(path: Path) -> str:
    return path.resolve().relative_to(analyze_service.DATA_DIR.resolve()).as_posix()


def run_batch(db: Session, request: schemas.BatchAnalyzeRequest) -> schemas.BatchSummary:
    folder = resolve_folder(request.folder)
    batch_id = new_batch_id()

    files = scan_images(folder, recursive=request.recursive)
    if request.limit is not None:
        files = files[: request.limit]

    for path in files:
        _process_one(db, batch_id=batch_id, path=path, request=request)

    return build_batch_summary(db, batch_id, folder=str(folder))


def _process_one(
    db: Session,
    *,
    batch_id: str,
    path: Path,
    request: schemas.BatchAnalyzeRequest,
) -> None:
    file_hash = sha256_file(path)

    duplicate_of = crud.find_batch_image_by_hash(db, file_hash)
    if duplicate_of is not None:
        crud.create_batch_image(
            db,
            batch_id=batch_id,
            original_path=str(path),
            filename=path.name,
            file_hash=file_hash,
            status="duplicate",
        )
        return

    row = crud.create_batch_image(
        db,
        batch_id=batch_id,
        original_path=str(path),
        filename=path.name,
        file_hash=file_hash,
        status="pending",
    )

    try:
        raw_bytes = path.read_bytes()
        result = analyze_service.analyze_image(
            db=db,
            upload=_FakeUpload(path.name),
            raw_bytes=raw_bytes,
            camera_id=request.camera_id,
            detection_threshold=request.detection_threshold,
        )
    except analyze_service.InvalidImageError as exc:
        crud.update_batch_image(db, row, status="failed", error=str(exc))
        return
    except AIModelUnavailableError as exc:
        crud.update_batch_image(db, row, status="failed", error=str(exc))
        return
    except Exception as exc:  # noqa: BLE001 -- one bad file must not kill the batch
        crud.update_batch_image(db, row, status="failed", error=str(exc))
        return

    if not result.animal_detected:
        # Blank frame: quarantine the ORIGINAL file (move, never delete).
        dest = _quarantine_destination(batch_id, path.name)
        shutil.move(str(path), str(dest))
        crud.update_batch_image(
            db,
            row,
            status="quarantined",
            reason="no_animal_detected",
            quarantine_path=_relative_to_data(dest),
        )
        return

    if result.sighting_id is not None:
        crud.update_batch_image(
            db,
            row,
            status="processed",
            sighting_id=result.sighting_id,
            tiger_id=result.tiger_id,
            match_status=result.match_status,
            best_similarity=result.best_similarity,
            crop_path=result.crop_path,
            embedding_path=result.embedding_path,
        )
    else:
        # REVIEW / POSSIBLE_NEW -- animal found, but no automatic tiger
        # decision. Original file is left in place (it's not a blank);
        # crop/embedding are already saved on disk for the human-review
        # workflow to reuse.
        crud.update_batch_image(
            db,
            row,
            status="needs_review",
            match_status=result.match_status,
            best_similarity=result.best_similarity,
            crop_path=result.crop_path,
            embedding_path=result.embedding_path,
        )


def build_batch_summary(db: Session, batch_id: str, folder: str) -> schemas.BatchSummary:
    rows = crud.get_batch_images(db, batch_id)
    counts = {"processed": 0, "needs_review": 0, "quarantined": 0, "duplicate": 0, "failed": 0}
    for r in rows:
        if r.status in counts:
            counts[r.status] += 1

    return schemas.BatchSummary(
        batch_id=batch_id,
        folder=folder,
        total_files=len(rows),
        processed=counts["processed"],
        needs_review=counts["needs_review"],
        quarantined=counts["quarantined"],
        duplicate=counts["duplicate"],
        failed=counts["failed"],
        images=[schemas.BatchImageOut.model_validate(r) for r in rows],
    )


def restore_quarantined(db: Session, image_row_id: int) -> schemas.RestoreResponse:
    row = crud.get_batch_image(db, image_row_id)
    if row is None or row.status != "quarantined" or not row.quarantine_path:
        raise RestoreNotFoundError(
            f"No quarantined batch image with id {image_row_id}."
        )

    src = analyze_service.DATA_DIR / row.quarantine_path
    dest = Path(row.original_path)

    if dest.exists():
        raise RestoreConflictError(
            f"Cannot restore: a file already exists at '{dest}'."
        )

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))

    crud.update_batch_image(db, row, status="restored", quarantine_path=None)

    return schemas.RestoreResponse(
        id=row.id, filename=row.filename, restored_to=str(dest), status="restored"
    )
