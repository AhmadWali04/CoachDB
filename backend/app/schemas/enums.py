"""Single source of truth for every allowed value in the contract.

Do not repeat these literals elsewhere. The frontend gets them through the
generated OpenAPI types.
"""

from enum import StrEnum


class TeamId(StrEnum):
    BLUE = "blue"
    RED = "red"


class PitchSide(StrEnum):
    """Which half a team defends. `top` attacks toward y=100."""

    TOP = "top"
    BOTTOM = "bottom"


class Formation(StrEnum):
    F433 = "4-3-3"
    F4231 = "4-2-3-1"
    F442 = "4-4-2"


class Mentality(StrEnum):
    BALANCED = "balanced"
    ATTACKING = "attacking"
    DEFENSIVE = "defensive"


class Level(StrEnum):
    """Used for pressing and defensive line height."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AttackFocus(StrEnum):
    """Relative to the team's own attacking direction."""

    MIDDLE = "middle"
    LEFT = "left"
    RIGHT = "right"


class Tempo(StrEnum):
    SLOW = "slow"
    NORMAL = "normal"
    FAST = "fast"


class PlayerRole(StrEnum):
    GK = "GK"
    DF = "DF"
    MF = "MF"
    FW = "FW"


class MatchPhase(StrEnum):
    NOT_STARTED = "not_started"
    FIRST_HALF = "first_half"
    HALFTIME = "halftime"
    SECOND_HALF = "second_half"
    FULL_TIME = "full_time"


class EventType(StrEnum):
    PASS_SEQUENCE = "pass_sequence"
    TURNOVER = "turnover"
    SHOT = "shot"
    GOAL = "goal"
    SAVE = "save"
    POSSESSION_CHANGE = "possession_change"
    PRESSING_SUCCESS = "pressing_success"
    COUNTERATTACK = "counterattack"
    FOUL = "foul"
    HALF_TIME = "half_time"
    FULL_TIME = "full_time"
    TACTICAL_CHANGE = "tactical_change"


class ActionStatus(StrEnum):
    PROPOSED = "proposed"
    SUBMITTED = "submitted"
    APPLIED = "applied"
    VERIFIED = "verified"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AudioStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    UNAVAILABLE = "unavailable"


class DependencyStatus(StrEnum):
    OK = "ok"
    NOT_CONFIGURED = "not_configured"
    UNREACHABLE = "unreachable"


class CrashPoint(StrEnum):
    AFTER_SUBMIT_BEFORE_VERIFY = "after_submit_before_verify"
