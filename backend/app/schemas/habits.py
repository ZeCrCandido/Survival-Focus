from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import HexColor


# ── Enums ─────────────────────────────────────────────────────────────────────


class HabitNature(str, Enum):
    healthy = "healthy"
    harmful = "harmful"


class HabitFrequency(str, Enum):
    daily  = "daily"
    weekly = "weekly"


# ── Skill schemas ─────────────────────────────────────────────────────────────


class HabitSkillCreate(BaseModel):
    skill_name:            str = Field(..., min_length=1, max_length=50)
    points_per_completion: int = Field(..., gt=0)


class HabitSkillResponse(BaseModel):
    id:                    UUID
    habit_id:              UUID
    skill_name:            str
    points_per_completion: int
    created_at:            datetime


# ── Request schemas ───────────────────────────────────────────────────────────


class HabitCreate(BaseModel):
    name:         str           = Field(..., min_length=1, max_length=100)
    description:  str | None   = Field(None, max_length=500)
    nature:       HabitNature
    frequency:    HabitFrequency = HabitFrequency.daily
    target_value: int | None   = Field(None, gt=0)
    unit:         str | None   = Field(None, max_length=20)
    color:        HexColor
    icon:         str | None   = Field(None, max_length=50)
    # Optional skill mappings — only valid when nature is healthy
    skills:       list[HabitSkillCreate] | None = None


class HabitUpdate(BaseModel):
    name:         str | None           = Field(None, min_length=1, max_length=100)
    description:  str | None           = Field(None, max_length=500)
    frequency:    HabitFrequency | None = None
    target_value: int | None           = Field(None, gt=0)
    unit:         str | None           = Field(None, max_length=20)
    color:        HexColor | None      = None
    icon:         str | None           = Field(None, max_length=50)


# ── Response schemas ──────────────────────────────────────────────────────────


class HabitResponse(BaseModel):
    id:           UUID
    user_id:      UUID
    name:         str
    description:  str | None
    nature:       HabitNature
    frequency:    HabitFrequency
    target_value: int | None
    unit:         str | None
    color:        str
    icon:         str | None
    is_active:    bool
    created_at:   datetime
    updated_at:   datetime


class HabitWithStats(HabitResponse):
    """Full habit detail — includes skill mappings and the live streak count."""
    skills:         list[HabitSkillResponse]
    current_streak: int


# ── Character impact ──────────────────────────────────────────────────────────


class PendingSkillReward(BaseModel):
    """
    Skill XP grants queued for the character module to apply.

    Embedded inside character_impact on the habit_log row — the same pattern
    as pending_rewards nested inside resources_earned on focus_sessions.
    The character module can query both tables uniformly:
      WHERE character_impact->>'pending_skill_rewards'->>'processed' = 'false'
    and flip processed=true after crediting the character sheet.
    """
    skills:    dict[str, int]  # skill_name → points_per_completion
    source:    str             # e.g. "habit_healthy_completed"
    processed: bool            # flipped to true by the character module


class CharacterImpact(BaseModel):
    health_delta: int
    energy_delta: int
    # Present only when a healthy habit is completed and has skill mappings.
    pending_skill_rewards: PendingSkillReward | None = None


# ── Log schemas ───────────────────────────────────────────────────────────────


class HabitLogCreate(BaseModel):
    was_completed: bool
    value:         int | None  = Field(None, ge=0)
    notes:         str | None  = Field(None, max_length=500)
    # Client may send the local calendar date; defaults to today UTC in the service.
    logged_at:     date | None = None


class HabitLogResponse(BaseModel):
    id:               UUID
    user_id:          UUID
    habit_id:         UUID
    logged_at:        date
    value:            int | None
    was_completed:    bool
    notes:            str | None
    character_impact: CharacterImpact | None
    created_at:       datetime


# ── Stats ─────────────────────────────────────────────────────────────────────


class WeeklyBreakdown(BaseModel):
    week_start: date
    total:      int
    completed:  int


class HabitLogStats(BaseModel):
    total_logs:       int
    total_completions: int
    total_missed:     int
    current_streak:   int
    longest_streak:   int
    completion_rate:  float           # 0.0–100.0
    weekly_breakdown: list[WeeklyBreakdown]  # last 8 weeks, oldest first


# ── Today's dashboard ─────────────────────────────────────────────────────────


class TodayHabitResponse(BaseModel):
    habit:          HabitResponse
    has_log_today:  bool
    was_completed:  bool | None  # None when has_log_today is False
    current_streak: int
