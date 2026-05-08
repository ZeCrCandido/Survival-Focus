from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Shared nested types ───────────────────────────────────────────────────────


class CharacterImpactDetail(BaseModel):
    """Health and energy deltas stored on a habit_log row."""
    health_delta: int
    energy_delta: int


class SkillRewardsDetail(BaseModel):
    """
    Skill-XP grants extracted from character_impact.pending_skill_rewards.
    Surfaced as a top-level field in API responses so callers never have to
    dig inside the JSONB structure themselves.
    """
    skills: dict[str, int]  # skill_name → points awarded
    source: str             # e.g. "habit_healthy_completed"


# ── Pending impacts ───────────────────────────────────────────────────────────


class PendingImpactItem(BaseModel):
    """One habit_log row that has not yet been consumed by the character module."""
    log_id:           UUID
    habit_id:         UUID
    habit_name:       str
    nature:           str                    # "healthy" | "harmful"
    logged_at:        date
    character_impact: CharacterImpactDetail
    skill_rewards:    SkillRewardsDetail | None  # None when no skill mappings triggered


class PendingImpactResponse(BaseModel):
    """Grouped list of all pending impacts for the authenticated user."""
    total_pending: int
    items:         list[PendingImpactItem]


# ── Process request / result ──────────────────────────────────────────────────


class ProcessImpactRequest(BaseModel):
    """
    Optional list of specific log IDs to process.
    When omitted (or null), ALL pending logs for the user are processed.
    """
    log_ids: list[UUID] | None = Field(
        None,
        description="Specific habit_log UUIDs to process. Omit to process everything pending.",
    )


class SkillRewardSummary(BaseModel):
    """Aggregated skill points across all logs processed in one call."""
    skill_name:   str
    total_points: int


class ProcessImpactResult(BaseModel):
    """
    Consolidated result returned to the caller (character module).

    The deltas are NOT applied here — this module only computes and marks.
    The character module applies total_health_delta / total_energy_delta to
    the character sheet and credits each skill_reward entry to the skill tree.
    """
    processed_count:   int
    total_health_delta: int
    total_energy_delta: int
    skill_rewards:     list[SkillRewardSummary]
    log_ids_processed: list[UUID]


# ── History ───────────────────────────────────────────────────────────────────


class ImpactHistoryItem(BaseModel):
    """One previously-processed habit_log entry."""
    log_id:           UUID
    habit_id:         UUID
    habit_name:       str
    nature:           str
    logged_at:        date
    processed_at:     datetime
    character_impact: CharacterImpactDetail
    skill_rewards:    SkillRewardsDetail | None


class ImpactHistoryResponse(BaseModel):
    """Paginated list of all processed impact entries."""
    items:  list[ImpactHistoryItem]
    total:  int
    limit:  int
    offset: int


# ── Summary ───────────────────────────────────────────────────────────────────


class HabitHealthRanking(BaseModel):
    """Per-habit aggregate used for top-N health impact rankings."""
    habit_id:           UUID
    habit_name:         str
    total_health_delta: int


class SkillPointsTotal(BaseModel):
    """Lifetime skill-XP total across all processed logs."""
    skill_name:   str
    total_points: int


class ImpactSummaryResponse(BaseModel):
    """Aggregate view of all habit impacts that have been processed so far."""
    total_health_delta:   int
    total_energy_delta:   int
    # Top 3 habits with the highest cumulative positive health contribution.
    top_positive_habits:  list[HabitHealthRanking]
    # Top 3 habits with the most negative cumulative health contribution.
    top_negative_habits:  list[HabitHealthRanking]
    # All-time skill XP earned through habits, grouped by skill name.
    skill_points_by_skill: list[SkillPointsTotal]
    # Count of logs still waiting to be processed — useful for UI badges.
    total_pending_count:  int
