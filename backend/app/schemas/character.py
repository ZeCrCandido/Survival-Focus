from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Stat & Skill responses ─────────────────────────────────────────────────────


class CharacterStatsResponse(BaseModel):
    health: int
    max_health: int
    energy: int
    max_energy: int
    hunger: int
    max_hunger: int
    hydration: int
    max_hydration: int
    last_fed_at: datetime | None = None
    last_hydrated_at: datetime | None = None
    last_healed_at: datetime | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class CharacterSkillResponse(BaseModel):
    skill_name: str
    current_points: int
    level: int
    points_to_next_level: int

    model_config = {"from_attributes": True}


class CharacterSkillsResponse(BaseModel):
    skills: list[CharacterSkillResponse]


# ── Equipment ──────────────────────────────────────────────────────────────────


class EquippedItemSummary(BaseModel):
    slot: str
    item_id: UUID
    item_name: str
    item_type: str

    model_config = {"from_attributes": True}


# ── Full character state ───────────────────────────────────────────────────────


class CharacterResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str | None = None
    level: int
    experience_points: int
    is_alive: bool
    death_count: int
    days_survived: int
    avatar_type_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    stats: CharacterStatsResponse
    skills: list[CharacterSkillResponse]
    equipment: list[EquippedItemSummary]
    pending_rewards_count: int

    model_config = {"from_attributes": True}


# ── Consumable request bodies ─────────────────────────────────────────────────


class FeedRequest(BaseModel):
    item_id: UUID


class HydrateRequest(BaseModel):
    item_id: UUID


class HealRequest(BaseModel):
    item_id: UUID


# ── Decay ──────────────────────────────────────────────────────────────────────


class DecayResponse(BaseModel):
    death_event: bool
    stats: CharacterStatsResponse


# ── Reward processing ─────────────────────────────────────────────────────────


class ResourcesGained(BaseModel):
    water: int = 0
    food: int = 0
    materials: int = 0


class SourceBreakdown(BaseModel):
    focus_session: int = 0
    habit_log: int = 0
    workout_session: int = 0
    sleep_session: int = 0


class RewardProcessingReport(BaseModel):
    processed_count: int
    total_health_delta: int
    total_energy_delta: int
    total_experience_gained: int
    levelled_up: bool
    new_level: int
    skills_levelled_up: list[str]
    resources_gained: ResourcesGained
    character_stats: CharacterStatsResponse
    source_breakdown: SourceBreakdown


class PendingRewardsResponse(BaseModel):
    total_pending: int
    by_source: dict[str, list[dict]]


# ── Journey ───────────────────────────────────────────────────────────────────


class LevelUpEvent(BaseModel):
    old_level: int
    new_level: int
    levelled_up_at: datetime

    model_config = {"from_attributes": True}


class JourneyResponse(BaseModel):
    character_age_days: int
    total_tasks_completed: int
    total_focus_minutes: int
    total_habits_logged: int
    total_workouts_completed: int
    total_sleep_nights_recorded: int
    total_resources_collected: ResourcesGained
    total_experience_earned: int
    level_progression: list[LevelUpEvent]
    current_streak_days: int = Field(
        description="Consecutive days with at least one completed task, habit log, workout, or sleep record"
    )
