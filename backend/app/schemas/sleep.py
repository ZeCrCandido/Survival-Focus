from datetime import date, datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class SleepQuality(str, Enum):
    poor      = "poor"
    fair      = "fair"
    good      = "good"
    excellent = "excellent"


class SleepGoalType(str, Enum):
    total_sleep_hours = "total_sleep_hours"
    deep_sleep_hours  = "deep_sleep_hours"
    rem_sleep_hours   = "rem_sleep_hours"
    sleep_consistency = "sleep_consistency"


# ── Shared nested ─────────────────────────────────────────────────────────────


class SleepCharacterImpact(BaseModel):
    health: int
    energy: int


# ── Notes ─────────────────────────────────────────────────────────────────────


class SleepNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)


class SleepNoteUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000, strip_whitespace=True)


class SleepNoteResponse(BaseModel):
    id:               UUID
    user_id:          UUID
    sleep_session_id: UUID
    content:          str
    created_at:       datetime
    updated_at:       datetime


# ── Sessions ──────────────────────────────────────────────────────────────────


class SleepSessionResponse(BaseModel):
    id:                   UUID
    user_id:              UUID
    external_date:        date
    source:               str
    sleep_start:          datetime
    sleep_end:            datetime
    in_bed_start:         datetime
    in_bed_end:           datetime
    total_sleep_hours:    float
    total_sleep_minutes:  int
    rem_hours:            float
    rem_minutes:          int
    deep_hours:           float
    deep_minutes:         int
    core_hours:           float
    core_minutes:         int
    awake_hours:          float
    awake_minutes:        int
    sleep_quality:        SleepQuality
    character_impact:     SleepCharacterImpact | None
    is_processed:         bool
    processed_at:         datetime | None
    created_at:           datetime
    updated_at:           datetime


class SleepSessionDetailResponse(SleepSessionResponse):
    """Full session detail including associated notes."""
    notes: list[SleepNoteResponse] = []


# ── Import ────────────────────────────────────────────────────────────────────


class SleepImportSummary(BaseModel):
    total_in_file:      int
    imported:           int
    skipped_duplicates: int
    failed:             int
    sessions:           list[SleepSessionResponse]


# ── Goals ─────────────────────────────────────────────────────────────────────


class SleepGoalCreate(BaseModel):
    goal_type:    SleepGoalType
    target_value: float = Field(..., gt=0)


class SleepGoalUpdate(BaseModel):
    target_value: float = Field(..., gt=0)


class SleepGoalResponse(BaseModel):
    id:           UUID
    user_id:      UUID
    goal_type:    SleepGoalType
    target_value: float
    created_at:   datetime
    updated_at:   datetime


class SleepGoalProgress(BaseModel):
    """A goal definition plus its current progress."""
    goal:             SleepGoalResponse
    current_value:    float
    target_value:     float
    progress_percent: float   # 0.0 – 100.0
    is_met:           bool


# ── Stats ─────────────────────────────────────────────────────────────────────


class SleepQualityBreakdown(BaseModel):
    poor:      int = 0
    fair:      int = 0
    good:      int = 0
    excellent: int = 0


class WeeklySleepSummary(BaseModel):
    week_start:           date
    nights:               int
    avg_total_sleep_hrs:  float
    avg_deep_hrs:         float
    avg_rem_hrs:          float


class BestWorstNight(BaseModel):
    external_date:     date
    total_sleep_hours: float
    sleep_quality:     SleepQuality


class SleepStatsResponse(BaseModel):
    total_nights:                    int
    avg_total_sleep_hours:           float | None
    avg_deep_hours:                  float | None
    avg_rem_hours:                   float | None
    avg_awake_hours:                 float | None
    best_night:                      BestWorstNight | None
    worst_night:                     BestWorstNight | None
    quality_breakdown:               SleepQualityBreakdown
    weekly_summary:                  list[WeeklySleepSummary]
    avg_sleep_consistency_minutes:   float | None


# ── Parser output ─────────────────────────────────────────────────────────────


class ParsedSleepEntry(BaseModel):
    """
    Internal representation of one parsed Apple Health sleep record.
    Produced by parsers/apple_health_sleep.py and consumed by services/sleep.py.
    Not exposed directly in any API response.
    """
    external_date:        str
    source:               str
    sleep_start:          datetime
    sleep_end:            datetime
    in_bed_start:         datetime
    in_bed_end:           datetime
    total_sleep_hours:    float
    total_sleep_minutes:  int
    rem_hours:            float
    rem_minutes:          int
    deep_hours:           float
    deep_minutes:         int
    core_hours:           float
    core_minutes:         int
    awake_hours:          float
    awake_minutes:        int
    sleep_quality:        str
    raw_data:             dict = Field(default_factory=dict)
