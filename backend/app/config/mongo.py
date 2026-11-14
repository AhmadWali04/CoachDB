"""MongoDB client shared by the whole backend. Repositories live in app/persistence."""

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

from app.schemas import DependencyStatus

from .settings import get_settings


@lru_cache
def get_client() -> MongoClient | None:
    uri = get_settings().mongodb_uri
    if uri is None or not uri.get_secret_value():
        return None
    return MongoClient(
        uri.get_secret_value(),
        appname="rival-coaches",
        serverSelectionTimeoutMS=3000,
        tz_aware=True,
    )


def get_db() -> Database:
    client = get_client()
    if client is None:
        raise RuntimeError("MONGODB_URI is not set; see .env.example")
    return client[get_settings().mongodb_database]


def ping() -> DependencyStatus:
    client = get_client()
    if client is None:
        return DependencyStatus.NOT_CONFIGURED
    try:
        client.admin.command("ping")
    except PyMongoError:
        return DependencyStatus.UNREACHABLE
    return DependencyStatus.OK
