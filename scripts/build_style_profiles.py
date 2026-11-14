#!/usr/bin/env python3
"""Download StatsBomb Open Data + Metrica sample data, build style profiles,
and optionally load them into MongoDB with the vector index (PRD §14.2).

    backend/.venv/bin/python scripts/build_style_profiles.py
    MONGODB_URI=... backend/.venv/bin/python scripts/build_style_profiles.py --load

Raw files are cached in backend/.cache/data/raw/ and never uploaded; only
derived profiles are written. A failed match or game is skipped with a
warning. Credit both sources wherever the profiles are shown.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.data import build_all_profiles, search_styles, write_profiles  # noqa: E402
from app.data.loader import STYLE_COLLECTION, load_style_profiles  # noqa: E402
from app.data.pipeline import (  # noqa: E402
    DEFAULT_METRICA_GAMES,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_STATSBOMB_COMPETITION,
    DEFAULT_STATSBOMB_MAX_MATCHES,
)
from app.data.tactical_style import DIMENSIONS, EMBEDDING_MODEL, style_query_vector  # noqa: E402
from app.schemas import ObservedTactics  # noqa: E402

SOURCES = (
    "Sources: StatsBomb Open Data (github.com/statsbomb/open-data), "
    "Metrica Sports sample data (github.com/metrica-sports/sample-data)."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--competition", type=int, default=DEFAULT_STATSBOMB_COMPETITION[0])
    parser.add_argument("--season", type=int, default=DEFAULT_STATSBOMB_COMPETITION[1])
    parser.add_argument("--max-matches", type=int, default=DEFAULT_STATSBOMB_MAX_MATCHES)
    parser.add_argument("--no-metrica", action="store_true")
    parser.add_argument("--load", action="store_true", help="upsert into MongoDB and index")
    parser.add_argument("--database", default=os.environ.get("MONGODB_DATABASE", "rival_coaches"))
    return parser.parse_args()


async def smoke_query(uri: str, database: str) -> None:
    from pymongo import AsyncMongoClient

    query = ObservedTactics(formation="4-3-3", pressing="high", defensive_line="high")
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=3000, tz_aware=True)
    try:
        hits = await search_styles(
            client[database][STYLE_COLLECTION],
            style_query_vector(query),
            embedding_model=EMBEDDING_MODEL,
            dimensions=DIMENSIONS,
            limit=3,
        )
    finally:
        await client.close()
    print("\nSmoke query (4-3-3, high press, high line):")
    if not hits:
        print("  no results (is the index queryable?)")
    for hit in hits:
        print(f"  {hit.score:.3f}  {hit.summary}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    args = parse_args()

    profiles = build_all_profiles(
        statsbomb_competition=(args.competition, args.season),
        statsbomb_max_matches=args.max_matches,
        metrica_games=() if args.no_metrica else DEFAULT_METRICA_GAMES,
    )
    if not profiles:
        print("No profiles were built -- check network access and try again.", file=sys.stderr)
        sys.exit(1)

    written_to = write_profiles(profiles, args.out)
    print(f"Wrote {len(profiles)} style profiles to {written_to}")
    for profile in profiles:
        print(f"  {profile.profile_id:<28} {profile.summary}")

    if args.load:
        uri = os.environ.get("MONGODB_URI")
        if not uri:
            print("--load needs MONGODB_URI in the environment.", file=sys.stderr)
            sys.exit(1)
        from pymongo import MongoClient

        client = MongoClient(uri, serverSelectionTimeoutMS=5000, tz_aware=True)
        try:
            result = load_style_profiles(
                client[args.database][STYLE_COLLECTION], [p.to_dict() for p in profiles]
            )
        finally:
            client.close()
        print(
            f"\nLoaded into {args.database}.{STYLE_COLLECTION}: {result.upserted} new, "
            f"{result.modified} updated, {result.removed} removed; index {result.index_status}"
        )
        asyncio.run(smoke_query(uri, args.database))

    print("\n" + SOURCES)


if __name__ == "__main__":
    main()
