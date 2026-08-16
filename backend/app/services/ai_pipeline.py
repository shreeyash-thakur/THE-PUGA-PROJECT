"""
Thin wrapper around the project's EXISTING MegaDetector + MegaDescriptor
code, so the backend can call it without duplicating any model/transform
logic.

Nothing in this module runs at import time except cheap stdlib/pathlib
code -- torch, timm, and megadetector_ai are only imported the first time
a detector/model is actually requested. This means:

  - The FastAPI app (and its tests) can start up fine even in an
    environment that doesn't have the (heavy, GPU-oriented) AI
    dependencies installed -- only the /api/analyze endpoint needs them.
  - Model weights are loaded once per process and cached (see the
    `_state` dict below), not reloaded on every request.

Detection format and the MegaDescriptor preprocessing here intentionally
mirror what's already in the repo:
  - detection formatting matches MegaDetector/src/megadetector_ai/cli.py's
    `_format_detections` (category names, xyxy bbox, confidence).
  - MegaDescriptor-L-384 preprocessing (resize 384x384, mean=std=0.5)
    matches the corrected version in MegaDetector/test_tiger_reid.py and
    MegaDetector/test_cropped_reid.py (the ImageNet stats used in the
    older test_reid.py / test_megadescriptor.py were a known bug -- see
    the comments in test_tiger_reid.py).

No matching threshold lives here. This module only produces embeddings
and can score similarity between two embeddings -- deciding what counts
as "the same tiger" is left to a human / a future task, per the project
requirements.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional, TypedDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # .../THE PUGA PROJECT
MEGADETECTOR_SRC = PROJECT_ROOT / "MegaDetector" / "src"

MEGADESCRIPTOR_MODEL_NAME = "hf-hub:BVRA/MegaDescriptor-L-384"
MEGADESCRIPTOR_IMAGE_SIZE = 384

# 0/1/2 class-id convention matches megadetector_ai's own CLI formatting.
CLASS_NAMES = {0: "animal", 1: "person", 2: "vehicle"}


class Detection(TypedDict):
    category: str
    confidence: float
    bbox: list  # [x1, y1, x2, y2]


class AIModelUnavailableError(RuntimeError):
    """Raised when the AI dependencies (torch/timm/megadetector_ai) or
    their model weights aren't available in this environment. The AI
    stack is intentionally separate from the base backend requirements
    (see backend/README.md), so this is an expected, recoverable error
    for environments that only run the plain CRUD API."""


# Process-wide cache so models are loaded once, not per-request.
_state = {"detector": None, "descriptor_model": None, "transform": None}


def _ensure_megadetector_importable() -> None:
    """Make the repo's `megadetector_ai` package importable. Prefers a
    normal installed package (e.g. `pip install -e ./MegaDetector`); falls
    back to putting MegaDetector/src on sys.path directly so this works
    out of the box for a hackathon checkout too."""
    try:
        import megadetector_ai  # noqa: F401
        return
    except ImportError:
        pass

    if MEGADETECTOR_SRC.exists() and str(MEGADETECTOR_SRC) not in sys.path:
        sys.path.insert(0, str(MEGADETECTOR_SRC))

    try:
        import megadetector_ai  # noqa: F401
    except ImportError as exc:
        raise AIModelUnavailableError(
            "Could not import 'megadetector_ai'. Install the AI "
            "dependencies (see MegaDetector/environment.yaml or "
            "MegaDetector/pyproject.toml) in this Python environment, "
            "e.g.: pip install -e ./MegaDetector"
        ) from exc


def get_detector(device: Optional[str] = None):
    """Lazily load & cache MegaDetectorV6, reusing the exact class from
    megadetector_ai (no reimplementation)."""
    if _state["detector"] is not None:
        return _state["detector"]

    _ensure_megadetector_importable()

    try:
        import torch
        from megadetector_ai import MegaDetectorV6
    except ImportError as exc:
        raise AIModelUnavailableError(
            f"AI dependency missing: {exc}. See backend/README.md for the "
            "separate AI environment this endpoint requires."
        ) from exc

    resolved_device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")

    try:
        model = MegaDetectorV6(
    device=resolved_device,
    pretrained=True,
    version="MDV6-yolov9-c",
)
    except Exception as exc:  # model download / weights problem
        raise AIModelUnavailableError(
            f"Failed to load MegaDetectorV6 weights: {exc}"
        ) from exc

    _state["detector"] = model
    return model


def get_descriptor():
    """Lazily load & cache MegaDescriptor-L-384 + its image transform."""
    if _state["descriptor_model"] is not None:
        return _state["descriptor_model"], _state["transform"]

    try:
        import timm
        from torchvision import transforms
    except ImportError as exc:
        raise AIModelUnavailableError(
            f"AI dependency missing: {exc}. See backend/README.md for the "
            "separate AI environment this endpoint requires."
        ) from exc

    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        model = timm.create_model(
            MEGADESCRIPTOR_MODEL_NAME, pretrained=True, num_classes=0
        )
    except Exception as exc:
        raise AIModelUnavailableError(
            f"Failed to load {MEGADESCRIPTOR_MODEL_NAME} weights: {exc}"
        ) from exc

    model = model.to(device)
    model.eval()

    # Mean=std=0.5, per MegaDescriptor-L-384's model card -- the corrected
    # normalization from MegaDetector/test_tiger_reid.py, not the older
    # ImageNet stats in test_reid.py / test_megadescriptor.py.
    transform = transforms.Compose(
        [
            transforms.Resize(
                (MEGADESCRIPTOR_IMAGE_SIZE, MEGADESCRIPTOR_IMAGE_SIZE)
            ),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.5, 0.5, 0.5], std=[0.5, 0.5, 0.5]),
        ]
    )

    _state["descriptor_model"] = model
    _state["transform"] = transform
    return model, transform


def run_detection(image_path: Path, threshold: float = 0.2) -> list[Detection]:
    """Run MegaDetector on a single image. Mirrors the formatting in
    megadetector_ai/cli.py::_format_detections exactly, so downstream
    consumers (and anyone comparing against CLI output) see the same
    shape."""
    detector = get_detector()

    results = detector.single_image_detection(str(image_path))

    detections: list[Detection] = []
    raw = results.get("detections")
    if raw is not None:
        for xyxy, conf, cls_id in zip(raw.xyxy, raw.confidence, raw.class_id):
            if conf >= threshold:
                detections.append(
                    Detection(
                        category=CLASS_NAMES.get(int(cls_id), "unknown"),
                        confidence=round(float(conf), 4),
                        bbox=[round(float(v), 1) for v in xyxy],
                    )
                )
    return detections


def select_best_animal_detection(
    detections: list[Detection],
) -> Optional[Detection]:
    """Pick the single detection to crop + embed. We use highest
    confidence among category=="animal" detections -- the most reliable
    single box for a Re-ID embedding. (An alternative used elsewhere in
    this repo's exploratory scripts is largest bounding-box area; either
    is a reasonable heuristic for a hackathon demo, no threshold/identity
    decision is implied by this choice.)"""
    animals = [d for d in detections if d["category"] == "animal"]
    if not animals:
        return None
    return max(animals, key=lambda d: d["confidence"])


def crop_detection(image, bbox: list):
    """Crop a PIL image to an [x1, y1, x2, y2] box, clamped to the image
    bounds. Matches the corner-coordinate convention already used in
    MegaDetector/crop_tiger.py."""
    x1, y1, x2, y2 = (round(v) for v in bbox)
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(image.width, x2)
    y2 = min(image.height, y2)
    return image.crop((x1, y1, x2, y2))


def compute_embedding(crop_image):
    """Run MegaDescriptor-L-384 on a cropped PIL image and return a
    single, L2-normalized embedding tensor on CPU. Same steps as
    MegaDetector/test_tiger_reid.py::get_embedding."""
    import torch
    import torch.nn.functional as F

    model, transform = get_descriptor()
    device = next(model.parameters()).device

    tensor = transform(crop_image.convert("RGB")).unsqueeze(0).to(device)

    with torch.no_grad():
        embedding = model(tensor)

    embedding = F.normalize(embedding, p=2, dim=1)
    return embedding.cpu()


def save_embedding(embedding, path: Path) -> None:
    import torch

    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(embedding, path)


def load_embedding(path: Path):
    import torch

    return torch.load(path, map_location="cpu")


def cosine_similarity(embedding_a, embedding_b) -> float:
    import torch.nn.functional as F

    a = embedding_a.flatten().unsqueeze(0)
    b = embedding_b.flatten().unsqueeze(0)
    return round(float(F.cosine_similarity(a, b).item()), 4)
