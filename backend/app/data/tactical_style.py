"""Tactical style vector shared by style profiles and scout queries.

Embedding model: `tactical-style-v1`. No ML model is involved: each dimension
is a hand-defined, explainable tactic, so a profile built from StatsBomb or
Metrica events and a query built from the scout's `ObservedTactics` live in
the same space.

How it works
1. Each source adapter converts its events to `OnPitchEvent`s: metres on a
   105 x 68 pitch, oriented so the acting team attacks toward +x and y=0 is on
   its left. `tactical_features` then measures every source the same way.
2. `finalize_profiles` ranks each feature across the whole profile set
   (percentile 0..1), labels it by tertile (low/medium/high, ...), and centers
   it to -1..1 for the vector. Labels are therefore relative to the set.
3. `style_query_vector` maps the scout's labels onto the same centered scale
   (low = -2/3, medium = 0, high = +2/3). Unknown tactics stay 0, so they
   don't affect cosine similarity.

Cross-source comparison is approximate: StatsBomb and Metrica record events
differently. Treat matches as hints, as the retrieval module says.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.schemas import AttackFocus, Formation, Level, Mentality, ObservedTactics, Tempo

EMBEDDING_MODEL = "tactical-style-v1"

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0
FINAL_THIRD_X_M = 70.0
# A regain beyond this x is in the opponent's 60% of the pitch (a high regain).
HIGH_REGAIN_X_M = 42.0
# An opponent pass starting before this x (in its own frame) is build-up play
# in its own 60%; together these give a PPDA-style pressing rate.
OPPONENT_BUILDUP_X_M = 63.0
LEFT_LANE_MAX_Y_M = PITCH_WIDTH_M / 3
RIGHT_LANE_MIN_Y_M = 2 * PITCH_WIDTH_M / 3
# Possession time is credited from one on-ball event to the next, capped so
# stoppages don't count as possession.
POSSESSION_GAP_CAP_S = 15.0

FORMATION_WEIGHT = 0.5
SUPPORTED_FORMATIONS: tuple[Formation, ...] = (Formation.F433, Formation.F4231, Formation.F442)

DIMENSION_NAMES: tuple[str, ...] = (
    "pressing",
    "defensive_line",
    "tempo",
    "mentality",
    "attack_lateral",  # -1 = left, +1 = right
    "attack_central",
    *(f"formation_{f.value}" for f in SUPPORTED_FORMATIONS),
)
DIMENSIONS = len(DIMENSION_NAMES)

TACTICAL_FEATURE_NAMES: tuple[str, ...] = (
    "press_rate",
    "regain_height_m",
    "passes_per_possession_min",
    "final_third_share",
    "left_entry_share",
    "middle_entry_share",
    "right_entry_share",
)

EventKind = Literal["pass", "shot", "regain"]


@dataclass(frozen=True)
class OnPitchEvent:
    """One event, in metres, from the acting team's attacking perspective."""

    team: str
    kind: EventKind
    t: float
    x: float
    y: float
    end_x: float | None = None
    end_y: float | None = None


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _ratio(num: float, den: float) -> float | None:
    return num / den if den else None


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def _entries(events: Sequence[OnPitchEvent]) -> list[OnPitchEvent]:
    return [
        e
        for e in events
        if e.kind == "pass"
        and e.end_x is not None
        and e.x < FINAL_THIRD_X_M <= e.end_x
        and e.end_y is not None
    ]


def tactical_features(events: Sequence[OnPitchEvent], team: str) -> dict[str, float | None]:
    """Measure one team's tactics from a whole match. Missing evidence is None."""
    ordered = sorted(events, key=lambda e: e.t)
    own = [e for e in ordered if e.team == team]
    opp = [e for e in ordered if e.team != team]

    on_ball = [e for e in ordered if e.kind in ("pass", "shot")]
    possession_s = 0.0
    for current, following in zip(on_ball, on_ball[1:], strict=False):
        if current.team == team:
            possession_s += min(max(following.t - current.t, 0.0), POSSESSION_GAP_CAP_S)

    own_passes = [e for e in own if e.kind == "pass"]
    regains = [e for e in own if e.kind == "regain"]
    opp_buildup = [e for e in opp if e.kind == "pass" and e.x < OPPONENT_BUILDUP_X_M]
    own_entries = _entries(own)
    opp_entries = _entries(opp)

    left = sum(1 for e in own_entries if e.end_y < LEFT_LANE_MAX_Y_M)
    right = sum(1 for e in own_entries if e.end_y > RIGHT_LANE_MIN_Y_M)
    middle = len(own_entries) - left - right
    n_entries = len(own_entries)

    return {
        "press_rate": _round(
            _ratio(sum(1 for e in regains if e.x > HIGH_REGAIN_X_M), len(opp_buildup))
        ),
        "regain_height_m": _round(_mean([e.x for e in regains]), 2),
        "passes_per_possession_min": _round(_ratio(len(own_passes), possession_s / 60), 2),
        "final_third_share": _round(_ratio(n_entries, n_entries + len(opp_entries))),
        "left_entry_share": _round(_ratio(left, n_entries)),
        "middle_entry_share": _round(_ratio(middle, n_entries)),
        "right_entry_share": _round(_ratio(right, n_entries)),
    }


# --- Cohort ranking ---------------------------------------------------------


def percentile_ranks(values: Sequence[float | None]) -> list[float | None]:
    """Mid-rank percentile in (0, 1); None stays None."""
    present = [v for v in values if v is not None]
    n = len(present)
    ranks: list[float | None] = []
    for v in values:
        if v is None or n == 0:
            ranks.append(None)
            continue
        below = sum(1 for other in present if other < v)
        equal = sum(1 for other in present if other == v)
        ranks.append((below + 0.5 * equal) / n)
    return ranks


def tertile(p: float | None, labels: tuple[str, str, str]) -> str | None:
    if p is None:
        return None
    return labels[0] if p < 1 / 3 else labels[1] if p < 2 / 3 else labels[2]


def _centered(p: float | None) -> float:
    return 0.0 if p is None else round(2 * p - 1, 4)


LEVELS = (Level.LOW.value, Level.MEDIUM.value, Level.HIGH.value)
TEMPOS = (Tempo.SLOW.value, Tempo.NORMAL.value, Tempo.FAST.value)
MENTALITIES = (Mentality.DEFENSIVE.value, Mentality.BALANCED.value, Mentality.ATTACKING.value)


def _formation_dims(formation: str | None) -> list[float]:
    return [FORMATION_WEIGHT if formation == f.value else 0.0 for f in SUPPORTED_FORMATIONS]


def _attack_focus(features: dict[str, float | None]) -> str | None:
    shares = {
        AttackFocus.LEFT.value: features.get("left_entry_share"),
        AttackFocus.MIDDLE.value: features.get("middle_entry_share"),
        AttackFocus.RIGHT.value: features.get("right_entry_share"),
    }
    if any(v is None for v in shares.values()):
        return None
    return max(shares, key=lambda k: shares[k])


@dataclass(frozen=True)
class CohortResult:
    tactics: dict[str, str | None]
    style_vector: tuple[float, ...]


def rank_cohort(
    features: Sequence[dict[str, float | None]], formations: Sequence[str | None]
) -> list[CohortResult]:
    """Label and vectorize each profile relative to the whole set."""

    def column(name: str) -> list[float | None]:
        return [f.get(name) for f in features]

    def lateral(f: dict[str, float | None]) -> float | None:
        left, right = f.get("left_entry_share"), f.get("right_entry_share")
        return None if left is None or right is None else right - left

    pressing = percentile_ranks(column("press_rate"))
    # Tracking measures the defensive line directly; use it when every profile
    # in this set has it (Metrica with tracking), else the regain height.
    tracked = all(f.get("defensive_line_height_m") is not None for f in features)
    line = percentile_ranks(column("defensive_line_height_m" if tracked else "regain_height_m"))
    tempo = percentile_ranks(column("passes_per_possession_min"))
    mentality = percentile_ranks(column("final_third_share"))
    lateral_p = percentile_ranks([lateral(f) for f in features])
    central = percentile_ranks(column("middle_entry_share"))

    results = []
    for i, f in enumerate(features):
        tactics = {
            "formation": formations[i]
            if formations[i] in {x.value for x in SUPPORTED_FORMATIONS}
            else None,
            "pressing": tertile(pressing[i], LEVELS),
            "defensive_line": tertile(line[i], LEVELS),
            "tempo": tertile(tempo[i], TEMPOS),
            "mentality": tertile(mentality[i], MENTALITIES),
            "attack_focus": _attack_focus(f),
        }
        vector = (
            _centered(pressing[i]),
            _centered(line[i]),
            _centered(tempo[i]),
            _centered(mentality[i]),
            _centered(lateral_p[i]),
            _centered(central[i]),
            *_formation_dims(formations[i]),
        )
        results.append(CohortResult(tactics=tactics, style_vector=vector))
    return results


# --- Scout query ---------------------------------------------------------------

_SCALE = {0: -2 / 3, 1: 0.0, 2: 2 / 3}


def _ordinal(value: str | None, labels: tuple[str, str, str]) -> float:
    return 0.0 if value is None else _SCALE[labels.index(value)]


def style_query_vector(observed: ObservedTactics) -> list[float] | None:
    """Encode the scout's inferred rival tactics. None when nothing is known."""
    focus = observed.attack_focus.value if observed.attack_focus else None
    lateral = {"left": -2 / 3, "right": 2 / 3}.get(focus or "", 0.0)
    central = {"middle": 2 / 3, "left": -1 / 3, "right": -1 / 3}.get(focus or "", 0.0)

    def label(v: object) -> str | None:
        return None if v is None else getattr(v, "value", v)

    vector = [
        _ordinal(label(observed.pressing), LEVELS),
        _ordinal(label(observed.defensive_line), LEVELS),
        _ordinal(label(observed.tempo), TEMPOS),
        _ordinal(label(observed.mentality), MENTALITIES),
        lateral,
        central,
        *_formation_dims(label(observed.formation)),
    ]
    vector = [round(v, 4) for v in vector]
    return vector if any(vector) else None


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0
