import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError

from app.api import demo, evaluations, matches
from app.config.mongo import ping
from app.config.settings import get_settings
from app.orchestration.dependencies import get_engine
from app.schemas import HealthResponse
from app.voice import AUDIO_CACHE_DIR


@asynccontextmanager
async def lifespan(app):
    engine = None
    try:
        engine = get_engine()
    except HTTPException:
        logging.getLogger(__name__).warning("engine waiting for MongoDB configuration/connectivity")
    yield
    if engine is not None:
        engine.close()
        get_engine.cache_clear()


VERSION = "0.1.0"


def create_app() -> FastAPI:
    app = FastAPI(title="Rival Coaches API", version=VERSION, lifespan=lifespan)

    @app.exception_handler(PyMongoError)
    async def database_error(request: Request, error: PyMongoError):
        return JSONResponse(status_code=503, content={"detail": "MongoDB temporarily unavailable"})

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
