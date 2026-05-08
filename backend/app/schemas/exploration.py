from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Skills ────────────────────────────────────────────────────────────────────


class HabitContribution(BaseModel):
    habit_id: UUID
    habit_name: str
    skill_name: str
    points_per_completion: int


class SkillResponse(BaseModel):
    skill_name: str
    level: int
    current_points: int
    points_to_next_level: int
    progress_percentage: float = Field(description="0–100 percentage to next level")
    description: str
    current_unlocks: list[str] = Field(description="Abilities unlocked at or below current level")
    next_unlock: str | None = Field(description="Next ability — None if at max tier")


class SkillDetailResponse(SkillResponse):
    total_points_ever_earned: int = Field(
        description="Sum of all skill_rewards[skill_name] across processed pending_rewards"
    )
    contributing_habits: list[HabitContribution]


# ── Areas ─────────────────────────────────────────────────────────────────────


class ExplorationAreaResponse(BaseModel):
    name: str
    description: str
    difficulty: str
    min_character_level: int
    min_skill_requirements: dict[str, int] | None
    possible_resources: list[str]
    possible_discoveries: list[str]
    is_unlocked: bool


# ── Explorations ──────────────────────────────────────────────────────────────


class ExplorationStartRequest(BaseModel):
    area_name: str


class DiscoveryResponse(BaseModel):
    id: UUID
    exploration_id: UUID
    character_id: UUID
    discovery_type: str
    name: str
    description: str | None = None
    rarity: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExplorationResponse(BaseModel):
    id: UUID
    character_id: UUID
    area_name: str
    difficulty: str
    status: str
    adventure_impact_score: int
    started_at: datetime
    ended_at: datetime | None = None
    was_successful: bool | None = None
    resources_found: dict | None = None
    experience_earned: int | None = None
    created_at: datetime
    discoveries: list[DiscoveryResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class RewardSummary(BaseModel):
    experience_earned: int
    resources_found: dict | None
    discoveries_count: int
    pending_reward_created: bool


class ExplorationCompleteResponse(BaseModel):
    exploration: ExplorationResponse
    discoveries: list[DiscoveryResponse]
    reward_summary: RewardSummary
    success_chance: float
    was_successful: bool


# ── Adventure estimate ────────────────────────────────────────────────────────


class TaskContribution(BaseModel):
    task_title: str
    impact: int
    completed_at: str


class AreaEstimate(BaseModel):
    area_name: str
    difficulty: str
    success_chance: float
    is_unlocked: bool


class AdventureEstimateResponse(BaseModel):
    current_impact_score: int
    task_contributions: list[TaskContribution]
    area_estimates: list[AreaEstimate]


# ── Stats ─────────────────────────────────────────────────────────────────────


class DiscoveryBreakdown(BaseModel):
    discovery_type: str
    count: int


class ExplorationStatsResponse(BaseModel):
    total_attempted: int
    total_successful: int
    total_failed: int
    success_rate_pct: float
    total_resources_found: dict
    total_experience_earned: int
    discoveries_by_type: list[DiscoveryBreakdown]
    favourite_area: str | None
    best_exploration_id: UUID | None
