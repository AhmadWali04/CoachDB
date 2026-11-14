from functools import lru_cache

from fastapi import HTTPException
from pymongo.errors import PyMongoError

from app.config.mongo import get_db
from app.config.settings import get_settings

from .engine import Engine


@lru_cache
def get_engine() -> Engine:
    try:
        engine = Engine(get_db(), get_settings())
        engine.start()
        return engine
    except (RuntimeError, PyMongoError) as error:
        raise HTTPException(
            503, "MongoDB unavailable; configure MONGODB_URI and check /health."
        ) from error
