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
│   └── routers/
│       ├── tigers.py
│       ├── sightings.py
│       └── cameras.py
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
