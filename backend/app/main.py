from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_storage, DATABASE_PATH
from app.routers import tigers, sightings, cameras
from app.schemas import Health

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Runs once on startup: creates the SQLite file, all tables, and the
    # local data/ directories if they don't already exist. No manual setup
    # step is required before running the server for the first time.
    init_storage()
    yield


app = FastAPI(
    title="PUGA API",
    description="Offline-first backend for the PUGA tiger Re-ID system.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tigers.router)
app.include_router(sightings.router)
app.include_router(cameras.router)


@app.get("/api/health", response_model=Health, tags=["health"])
def health_check():
    return Health(
        status="ok",
        database="connected" if DATABASE_PATH.exists() else "missing",
        mode="offline",
    )
