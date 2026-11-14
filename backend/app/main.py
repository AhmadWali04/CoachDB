from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import demo, evaluations, matches
from app.config.mongo import ping
from app.config.settings import get_settings
from app.schemas import HealthResponse
from app.voice import AUDIO_CACHE_DIR

VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(title="Rival Coaches API", version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"], operation_id="health")
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=VERSION, mongodb=ping())

    app.include_router(matches.router)
    app.include_router(demo.router)
    app.include_router(evaluations.router)

    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=AUDIO_CACHE_DIR), name="audio")
    return app


app = create_app()
