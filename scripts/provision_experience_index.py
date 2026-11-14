#!/usr/bin/env python3
"""Preview or explicitly provision the private coach-experience Vector Search index.

Dry-run by default. --apply reads MONGODB_URI/MONGODB_DATABASE from the environment
or backend/.env. Never prints credentials or reads/writes experience documents.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.config.settings import Settings  # noqa: E402
from app.data.experience_index import (  # noqa: E402
    EXPERIENCE_COLLECTION,
    IndexDefinitionMismatch,
    provision_experience_index,
)
from app.data.indexes import EXPERIENCE_INDEX, vector_index_definition  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dimensions",
        type=int,
        required=True,
        help="actual embedding dimensions agreed with Track A's experience writer",
    )
    parser.add_argument(
        "--apply", action="store_true", help="create missing collection/index"
    )
    parser.add_argument("--wait-seconds", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        definition = vector_index_definition(args.dimensions, experiences=True)
        if not 0 < args.wait_seconds <= 300:
            raise ValueError("--wait-seconds must be greater than zero and at most 300")
    except ValueError as error:
        parser.error(str(error))
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry-run",
                    "collection": EXPERIENCE_COLLECTION,
                    "name": EXPERIENCE_INDEX,
                    "type": "vectorSearch",
                    "definition": definition,
                },
                indent=2,
            )
        )
        return 0

    # Imported lazily: previewing needs neither a connection nor credentials.
    from pymongo import MongoClient
    from pymongo.errors import PyMongoError

    settings = Settings(_env_file=REPO_ROOT / "backend" / ".env")
    uri = settings.mongodb_uri
    if uri is None or not uri.get_secret_value():
        print(
            "MONGODB_URI is required for --apply (environment or backend/.env).",
            file=sys.stderr,
        )
        return 1
    try:
        with MongoClient(
            uri.get_secret_value(),
            appname="rival-coaches-index-setup",
            serverSelectionTimeoutMS=3000,
            connectTimeoutMS=3000,
            socketTimeoutMS=5000,
            tz_aware=True,
        ) as client:
            result = provision_experience_index(
                client[settings.mongodb_database],
                args.dimensions,
                timeout_s=args.wait_seconds,
            )
    except (IndexDefinitionMismatch, TimeoutError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except PyMongoError:
        # Driver exceptions may include a credential-bearing URI or host details.
        print(
            "MongoDB index setup failed; check connectivity, permissions and Atlas status.",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "collection": EXPERIENCE_COLLECTION,
                "index": EXPERIENCE_INDEX,
                "status": result.status,
                "created_collection": result.created_collection,
                "created_index": result.created_index,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
