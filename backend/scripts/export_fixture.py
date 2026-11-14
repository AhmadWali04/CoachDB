#!/usr/bin/env python3
"""Export one real simulator run to `frontend/src/fixtures/` (PRD §13.5,
CHECKLIST.md rule 7: fixtures must come from a real simulator run, never be
hand-invented).

    .venv/bin/python scripts/export_fixture.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import FramesPage, MatchPhase, TacticalSettings, TeamId  # noqa: E402
from app.simulator import run_match  # noqa: E402

SEED = 42
MATCH_ID = "match_seed42"
STEPS_PER_HALF = 20
OUT_PATH = (
    Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures" / "match_seed42.json"
)

BLUE_FIRST_HALF = TacticalSettings.model_validate(
    {
        "formation": "4-3-3",
        "mentality": "attacking",
        "pressing": "high",
        "defensive_line": "high",
        "attack_focus": "left",
        "tempo": "fast",
    }
)
RED_FIRST_HALF = TacticalSettings.model_validate(
    {
        "formation": "4-4-2",
        "mentality": "balanced",
        "pressing": "medium",
        "defensive_line": "medium",
        "attack_focus": "middle",
        "tempo": "normal",
    }
)
RED_SECOND_HALF = TacticalSettings.model_validate(
    {
        "formation": "4-2-3-1",
        "mentality": "defensive",
        "pressing": "low",
        "defensive_line": "low",
        "attack_focus": "right",
        "tempo": "slow",
    }
)


def main() -> None:
    result = run_match(
        MATCH_ID,
        SEED,
        BLUE_FIRST_HALF,
        RED_FIRST_HALF,
        steps_per_half=STEPS_PER_HALF,
        second_half_tactics={TeamId.RED: RED_SECOND_HALF},
    )

    page = FramesPage(
        match_id=MATCH_ID,
        frames=result.frames,
        next_seq=None,
        phase=MatchPhase.FULL_TIME,
        fixture=True,
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(page.model_dump_json(indent=2) + "\n")
    print(f"Wrote {len(result.frames)} frames to {OUT_PATH}")
    print(f"Final score: blue {result.final_state.score.blue} - red {result.final_state.score.red}")


if __name__ == "__main__":
    main()
