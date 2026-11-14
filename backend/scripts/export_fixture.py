"""Record one real seeded simulator run as a frontend fixture (CHECKLIST rule 7).

    .venv/bin/python scripts/export_fixture.py [seed]

Writes frontend/src/fixtures/match_seed<seed>.json as a FramesPage with
`fixture: true`, so the UI shows its fixture badge. No coaches run: the second
half uses first-half tactics. Nothing in the file is hand-written.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas import FramesPage  # noqa: E402
from app.simulator import simulate_match  # noqa: E402

seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
state, _, frames = simulate_match(f"fixture_seed{seed}", seed)
page = FramesPage(
    match_id=state.match_id, frames=frames, next_seq=None, phase=state.phase, fixture=True
)
fixtures = Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures"
out = fixtures / f"match_seed{seed}.json"
out.write_text(page.model_dump_json(exclude_none=False))
print(f"wrote {out} ({len(frames)} frames, final score {state.score.blue}-{state.score.red})")
