from datetime import datetime
from typing import Literal

from .base import Contract
from .enums import ActionStatus, TeamId
from .match import TacticalSettings


class Action(Contract):
    """Action ledger record (PRD §9). `submitted` is not success; only `verified` is."""

    action_id: str
    match_id: str
    team_id: TeamId
    kind: Literal["apply_tactical_plan"] = "apply_tactical_plan"
    requested: TacticalSettings
    expected_state_version: int
    status: ActionStatus
    simulator_ref: str | None = None
    observed_state_version: int | None = None
    fencing_token: int
    created_at: datetime
    updated_at: datetime
