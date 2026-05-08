from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DashboardCharacter(BaseModel):
    id: UUID
    name: str | None = None
    level: int
    experience_points: int
    experience_to_next_level: int
    xp_progress_pct: float = Field(description="0–100 percentage to next level")
    is_alive: bool
    death_count: int
    health: int
    max_health: int
    energy: int
    max_energy: int
    hunger: int
    hydration: int
    last_fed_at: datetime | None = None
    last_hydrated_at: datetime | None = None
    hunger_critical: bool
    hydration_critical: bool
    health_critical: bool
    energy_low: bool


class DashboardTagSummary(BaseModel):
    id: UUID
    name: str
    color: str


class DashboardInProgressTask(BaseModel):
    id: UUID
    user_id: UUID
    category_id: UUID | None = None
    title: str
    description: str | None = None
    priority: str
    status: str
    focus_type: str
    due_date: datetime | None = None
    completed_at: datetime | None = None
    estimated_adventure_impact: int | None = None
    tags: list[DashboardTagSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DashboardActiveFocusSession(BaseModel):
    id: UUID
    task_id: UUID | None = None
    type: str
    started_at: datetime


class DashboardCriticalTask(BaseModel):
    id: UUID
    title: str
    priority: str
    due_date: datetime | None = None
    estimated_adventure_impact: int | None = None


class DashboardTasksToday(BaseModel):
    total_pending: int
    completed_today: int
    overdue_count: int
    in_progress: DashboardInProgressTask | None = None
    critical_pending: list[DashboardCriticalTask] = Field(default_factory=list)
    active_focus_session: DashboardActiveFocusSession | None = None


class DashboardPendingHabit(BaseModel):
    id: UUID
    name: str
    nature: str
    color: str | None = None
    icon: str | None = None


class DashboardHabitsToday(BaseModel):
    total_active_habits: int
    logged_today: int
    completed_today: int
    pending_today: list[DashboardPendingHabit] = Field(default_factory=list)
    completion_rate_today: float


class DashboardFocusResources(BaseModel):
    water: int = 0
    food: int = 0
    materials: int = 0


class DashboardFocusToday(BaseModel):
    sessions_today: int
    total_minutes_today: int
    completed_sessions_today: int
    resources_earned_today: DashboardFocusResources = Field(
        default_factory=DashboardFocusResources
    )


class DashboardSleepLast(BaseModel):
    external_date: str
    total_sleep_hours: float | None = None
    total_sleep_minutes: float | None = None
    rem_hours: float | None = None
    deep_hours: float | None = None
    core_hours: float | None = None
    awake_hours: float | None = None
    sleep_quality: str | None = None
    sleep_start: datetime | None = None
    sleep_end: datetime | None = None
    days_since: int


class DashboardWorkoutLast(BaseModel):
    name: str | None = None
    started_at: datetime
    duration_seconds: int | None = None
    distance_km: float | None = None
    active_energy_kcal: float | None = None
    avg_heart_rate: float | None = None
    effort_level: str | None = None
    days_since: int


class DashboardRewardsBreakdown(BaseModel):
    focus_session: int = 0
    habit_log: int = 0
    workout_session: int = 0
    sleep_session: int = 0


class DashboardPendingRewards(BaseModel):
    total_pending: int
    has_unprocessed: bool
    breakdown: DashboardRewardsBreakdown = Field(default_factory=DashboardRewardsBreakdown)
    estimated_health_delta: int
    estimated_energy_delta: int


class DashboardNextArea(BaseModel):
    area_name: str
    difficulty: str
    success_chance: float


class DashboardExploration(BaseModel):
    is_active: bool
    area_name: str | None = None
    started_at: datetime | None = None
    current_impact_score: int | None = None
    was_successful: bool | None = None
    ended_at: datetime | None = None
    resources_found: dict | None = None
    next_area_estimate: DashboardNextArea | None = None


class DashboardOnboarding(BaseModel):
    is_completed: bool
    avatar_assigned: bool
    character_created: bool


class DashboardResponse(BaseModel):
    character: DashboardCharacter | None = None
    tasks_today: DashboardTasksToday
    habits_today: DashboardHabitsToday
    focus_today: DashboardFocusToday
    sleep_last: DashboardSleepLast | None = None
    workout_last: DashboardWorkoutLast | None = None
    pending_rewards: DashboardPendingRewards
    exploration: DashboardExploration
    onboarding: DashboardOnboarding
