from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import demo, matches
from app.config.mongo import ping
from app.config.settings import get_settings
from app.schemas import HealthResponse

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
    return app


app = create_app()
