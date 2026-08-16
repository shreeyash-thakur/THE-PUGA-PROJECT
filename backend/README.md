# PUGA Backend (offline SQLite foundation)

Offline-first FastAPI + SQLite backend for PUGA. No internet, Docker, or
cloud database required.

## Setup

From the `backend/` directory:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

## Run

```bash
python -m uvicorn app.main:app --reload
```

On first run this automatically creates:

- `backend/database/puga.db` (SQLite file + all tables)
- `backend/data/images/`, `backend/data/crops/`, `backend/data/embeddings/`

No manual database setup is needed.

- API base: http://127.0.0.1:8000
- Swagger docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

## Optional: seed test data

```bash
python seed.py
```

Creates `TIGER-001` / `TIGER-002`, two sample cameras, and a few sample
sightings (metadata only, no fake images/embeddings). Safe to re-run.

## AI pipeline integration (`/api/analyze`)

`POST /api/analyze` runs the full pipeline on an uploaded image:

```
image -> MegaDetector -> crop best animal detection -> MegaDescriptor-L-384
      -> embedding (.pt) -> similarity vs. stored embeddings -> SQLite rows
```

This reuses the project's existing `MegaDetector/src/megadetector_ai`
package and the corrected MegaDescriptor-L-384 preprocessing from
`MegaDetector/test_tiger_reid.py` (mean=std=0.5) — no model or transform
code is duplicated; see `app/services/ai_pipeline.py`.

**This endpoint needs extra, heavier dependencies** that are deliberately
*not* in `requirements.txt` (see `requirements-ai.txt`):

```bash
pip install -r requirements.txt
pip install -r requirements-ai.txt
pip install -e ../MegaDetector   # makes `megadetector_ai` importable
```

If these aren't installed, the base backend (all CRUD endpoints, `/api/health`,
Swagger, `pytest`) still works fine — only `/api/analyze` returns `503` with
a clear message telling you what's missing.

Request (multipart form):

| field | required | notes |
|---|---|---|
| `file` | yes | image file (`.jpg/.jpeg/.png/.bmp/.tif/.tiff/.webp`) |
| `tiger_id` | no | assign the sighting to this existing tiger instead of auto-creating one |
| `camera_id` | no | must already exist (`POST /api/cameras`) |
| `latitude`, `longitude`, `location_name` | no | |
| `detection_threshold` | no | default `0.2`, matches MegaDetector CLI default |

Response highlights:

- `animal_detected`, `detections`, `used_detection` — what MegaDetector found.
- `crop_path`, `embedding_id`, `embedding_path` — where the crop/embedding were saved.
- `tiger_id` + `tiger_status` (`"new"` or `"matched"`) — if `tiger_id` wasn't
  supplied, a new tiger is auto-created (status `"unidentified"`).
- `candidate_matches` — cosine similarity of the new embedding against every
  other tiger's stored embeddings, **highest first, no threshold applied**.
  This is informational only, not an automatic identification — matching
  logic is intentionally left for a later task.

`GET /api/analyze/{sighting_id}` returns the combined sighting + tiger +
embedding record produced by a previous analyze call.

## Tests

```bash
pip install pytest httpx
pytest -q
```

Tests run against a temporary SQLite file, never `database/puga.db`.

## Layout

```
backend/
├── app/
│   ├── main.py         # FastAPI app, CORS, startup DB init, /api/health
│   ├── database.py      # engine/session, path setup, init_storage()
│   ├── models.py        # Tiger, Camera, Sighting, Embedding tables
│   ├── schemas.py        # Pydantic request/response models
│   ├── crud.py          # DB access functions
│   ├── routers/
│   │   ├── tigers.py
│   │   ├── sightings.py
│   │   ├── cameras.py
│   │   └── analyze.py    # POST /api/analyze, GET /api/analyze/{sighting_id}
│   └── services/
│       ├── ai_pipeline.py     # MegaDetector + MegaDescriptor wrapper (lazy-loaded)
│       └── analyze_service.py # orchestrates upload -> AI -> DB
├── data/
│   ├── images/          # full camera-trap images
│   ├── crops/            # cropped animal/tiger images
│   └── embeddings/       # .pt embedding tensors (paths stored in DB, not blobs)
├── database/
│   └── puga.db           # created automatically on first run
├── tests/
│   └── test_api.py
├── seed.py
└── requirements.txt
```

## Design notes for connecting the AI pipeline later

- `Sighting.image_path` / `crop_path` / `embedding_path` store paths
  relative to `backend/data/`, not binary blobs. When the MegaDetector +
  MegaDescriptor pipeline produces a crop and a `.pt` embedding, save the
  files under `backend/data/crops/` and `backend/data/embeddings/`, then
  `POST /api/sightings` with those paths.
- `Embedding` rows are separate from `Sighting` rows (`sighting_id` is
  optional) so a tiger's reference/gallery embeddings can be stored without
  necessarily being tied to one specific sighting.
- No matching, thresholding, or automatic tiger-creation logic is
  implemented here on purpose — this task is the storage/API foundation
  only.
- All paths in `app/database.py` are resolved relative to the `backend/`
  folder itself (`Path(__file__).resolve()`), so the project can live
  anywhere on disk — nothing is hardcoded to a specific drive or folder
  name.
