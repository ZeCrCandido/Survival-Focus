from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class WorkoutEffortLevel(str, Enum):
    light    = "light"
    moderate = "moderate"
    hard     = "hard"
    max      = "max"


class WorkoutGoalType(str, Enum):
    distance_km        = "distance_km"
    active_energy_kcal = "active_energy_kcal"
    duration_minutes   = "duration_minutes"
    session_count      = "session_count"


class WorkoutGoalPeriod(str, Enum):
    daily   = "daily"
    weekly  = "weekly"
    monthly = "monthly"


# ── Shared nested types ───────────────────────────────────────────────────────


class WorkoutCharacterImpact(BaseModel):
    """Health and energy awarded when a workout is imported."""
    health: int
    energy: int


# ── Notes ─────────────────────────────────────────────────────────────────────


class WorkoutNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)


class WorkoutNoteUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)


class WorkoutNoteResponse(BaseModel):
    id:                 UUID
    user_id:            UUID
    workout_session_id: UUID
    content:            str
    created_at:         datetime
    updated_at:         datetime


# ── Sessions ──────────────────────────────────────────────────────────────────


class WorkoutSessionResponse(BaseModel):
    id:                   UUID
    user_id:              UUID
    external_id:          str | None
    name:                 str
    source:               str
    started_at:           datetime
    ended_at:             datetime
    duration_seconds:     int
    distance_km:          float | None
    active_energy_kcal:   float | None
    avg_heart_rate:       float | None
    max_heart_rate:       int   | None
    min_heart_rate:       int   | None
    avg_speed_kmh:        float | None
    step_cadence:         float | None
    total_steps:          int   | None
    temperature_celsius:  float | None
    humidity_percent:     float | None
    elevation_up_meters:  float | None
    intensity:            float | None
    effort_level:         WorkoutEffortLevel | None
    character_impact:     WorkoutCharacterImpact | None
    is_processed:         bool
    processed_at:         datetime | None
    created_at:           datetime
    updated_at:           datetime


class WorkoutSessionDetailResponse(WorkoutSessionResponse):
    """Full workout detail including associated notes."""
    notes: list[WorkoutNoteResponse] = []


# ── Import ────────────────────────────────────────────────────────────────────


class WorkoutImportSummary(BaseModel):
    total_in_file:      int
    imported:           int
    skipped_duplicates: int
    failed:             int
    sessions:           list[WorkoutSessionResponse]


# ── Goals ─────────────────────────────────────────────────────────────────────


class WorkoutGoalCreate(BaseModel):
    goal_type:    WorkoutGoalType
    period:       WorkoutGoalPeriod
    target_value: float = Field(..., gt=0)


class WorkoutGoalUpdate(BaseModel):
    target_value: float = Field(..., gt=0)


class WorkoutGoalResponse(BaseModel):
    id:           UUID
    user_id:      UUID
    goal_type:    WorkoutGoalType
    period:       WorkoutGoalPeriod
    target_value: float
    created_at:   datetime
    updated_at:   datetime


class WorkoutGoalProgress(BaseModel):
    """A goal definition plus its current-period progress."""
    goal:             WorkoutGoalResponse
    current_value:    float
    target_value:     float
    progress_percent: float  # 0.0 – 100.0
    is_met:           bool
    period_start:     date


# ── Stats ─────────────────────────────────────────────────────────────────────


class EffortBreakdown(BaseModel):
    light:    int = 0
    moderate: int = 0
    hard:     int = 0
    max:      int = 0
    unknown:  int = 0  # sessions without heart-rate data


class WeeklySummary(BaseModel):
    week_start:               date
    sessions:                 int
    total_distance_km:        float
    total_active_energy_kcal: float


class WorkoutStatsResponse(BaseModel):
    total_sessions:           int
    total_distance_km:        float
    total_active_energy_kcal: float
    total_duration_minutes:   float
    total_steps:              int
    avg_heart_rate:           float | None
    effort_breakdown:         EffortBreakdown
    most_frequent_type:       str | None
    weekly_summary:           list[WeeklySummary]  # last 8 weeks, oldest first
