from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class SessionType(str, Enum):
    pomodoro  = "pomodoro"
    stopwatch = "stopwatch"


# ── Nested schemas ────────────────────────────────────────────────────────────


class PendingRewards(BaseModel):
    """
    XP grant that the character module will read and mark as processed.
    Only present on completed pomodoro sessions.
    """
    xp:        int
    source:    str   # e.g. "pomodoro_completed"
    processed: bool  # flipped to true by the character module after applying XP


class ResourcesEarned(BaseModel):
    """Survival resources collected during a focus session."""
    water:     int = 0
    food:      int = 0
    materials: int = 0
    # Character XP queued for the next character-module processing cycle.
    # None for stopwatch sessions or abandoned pomodoros.
    pending_rewards: PendingRewards | None = None


class TypeStats(BaseModel):
    sessions: int
    minutes:  float


class TotalResources(BaseModel):
    """Aggregate resource totals — no pending_rewards at this level."""
    water:     int
    food:      int
    materials: int


# ── Request schemas ───────────────────────────────────────────────────────────


class FocusSessionStart(BaseModel):
    task_id: UUID
    type:    SessionType


class FocusSessionEnd(BaseModel):
    was_completed: bool


# ── Response schemas ──────────────────────────────────────────────────────────


class FocusSessionResponse(BaseModel):
    id:               UUID
    user_id:          UUID
    task_id:          UUID
    type:             SessionType
    started_at:       datetime
    ended_at:         datetime | None
    duration_seconds: int | None
    was_completed:    bool
    resources_earned: ResourcesEarned | None
    created_at:       datetime


class FocusStatsResponse(BaseModel):
    total_sessions:         int
    total_minutes:          float
    completed_sessions:     int
    abandoned_sessions:     int
    total_resources:        TotalResources
    average_session_minutes: float
    by_type:                dict[str, TypeStats]
