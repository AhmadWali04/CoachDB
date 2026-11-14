"""Render a `CoachView` (and retrieved memory) as compact prompt context.

Only fields of the view are rendered, so the guardrail that built the view
decides what a coach can know. Every fact carries the ID a coach must cite.
"""

from __future__ import annotations

import json
from collections.abc import Sequence

from app.data import ExperienceHit, StyleHit
from app.schemas import TeamStats
from app.schemas.coach_view import CoachView

METRIC_NAMES = (*TeamStats.model_fields, "score", "stamina", "clock_minute")


def allowed_evidence(
    view: CoachView,
    styles: Sequence[StyleHit] = (),
    experiences: Sequence[ExperienceHit] = (),
) -> set[str]:
    ids = {e.event_id for e in view.public_events}
    ids |= {f"metric:{name}" for name in METRIC_NAMES}
    ids |= {f"profile:{hit.profile_id}" for hit in styles}
    ids |= {f"experience:{hit.experience_id}" for hit in experiences}
    return ids


def render_view(view: CoachView) -> str:
    own, rival = view.own_team, view.rival_team
    data = {
        "match_id": view.match_id,
        "you_coach": own.team_id.value,
        "rival": rival.team_id.value,
        "phase": view.phase.value,
        "score": view.score.model_dump(),
        "stats": {team.value: stats.model_dump() for team, stats in view.stats.items()},
        "own_team": {
            "name": own.name,
            "attacks_toward": "y=100" if own.side.value == "top" else "y=0",
            "first_half_tactics": own.tactics.model_dump(mode="json"),
            "players": [
                {
                    "id": p.player_id,
                    "number": p.number,
                    "role": p.role.value,
                    "stamina": round(p.stamina, 2),
                    "available": p.available,
                }
                for p in own.players
            ],
        },
        "rival_team": {
            "name": rival.name,
            "kickoff_formation": rival.kickoff_formation.value,
            "players": [
                {"id": p.player_id, "number": p.number, "role": p.role.value} for p in rival.players
            ],
        },
        "first_half_events": [
            {
                "id": e.event_id,
                "min": e.clock_minute,
                "team": e.team_id.value if e.team_id else None,
                "type": e.type.value,
                "players": e.player_ids,
                **({"details": e.details} if e.details else {}),
            }
            for e in view.public_events
        ],
    }
    return json.dumps(data, separators=(",", ":"))


def render_styles(styles: Sequence[StyleHit]) -> str:
    if not styles:
        return "No similar historical styles were found."
    return "\n".join(
        f"- profile:{h.profile_id} (similarity {h.score:.2f}): {h.summary}" for h in styles
    )


def render_experiences(experiences: Sequence[ExperienceHit]) -> str:
    if not experiences:
        return "No relevant past experiences in your own memory."
    return "\n".join(
        f"- experience:{h.experience_id} (similarity {h.score:.2f}): {h.summary} "
        f"Verified outcome: {h.verified_outcome}"
        for h in experiences
    )
