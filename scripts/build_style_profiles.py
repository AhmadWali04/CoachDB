#!/usr/bin/env python3
"""Fetches a small, fixed sample of StatsBomb Open Data + Metrica Sports
sample data and derives compact team style profiles (PRD §14.2).

    python scripts/build_style_profiles.py [output_path]

Only derived features are written -- never the raw dataset files -- and
only from the two free, public sources credited in the UI's dataset
attribution panel. Requires network access; a single failed match/game is
skipped with a warning rather than failing the whole run.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.data import build_all_profiles, write_profiles  # noqa: E402
from app.data.pipeline import DEFAULT_OUTPUT_PATH  # noqa: E402


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_PATH

    profiles = build_all_profiles()
    if not profiles:
        print("No profiles were built -- check network access and try again.", file=sys.stderr)
        sys.exit(1)

    written_to = write_profiles(profiles, out_path)
    print(f"Wrote {len(profiles)} style profiles to {written_to}")
    for profile in profiles:
        print(f"  {profile.profile_id}  ({profile.source})  tags={profile.tags}")
    print("\nSources: StatsBomb Open Data (github.com/statsbomb/open-data), "
          "Metrica Sports sample data (github.com/metrica-sports/sample-data).")


if __name__ == "__main__":
    main()
