"""
Dashboard aggregation service.

Concurrency model
-----------------
supabase-py exposes a synchronous client. Each sub-query is implemented as a
plain sync function (_sync_fetch_*) and wrapped in asyncio.to_thread() so the
event loop can dispatch all nine queries to the thread-pool simultaneously.
asyncio.gather() then awaits all of them in parallel, reducing total wall-clock
time to roughly the duration of the slowest single query instead of the sum of
all nine.

Fault isolation
---------------
Every coroutine passed to asyncio.gather() is wrapped in _safe_gather() which
catches any exception, logs it with context, and returns the pre-defined safe
default for that section. A Supabase timeout on the workout query, for example,
will never crash the character section — the response arrives with
workout_last=null and all other sections fully populated.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from functools import partial

from app.core.supabase_client import get_supabase
from app.schemas.dashboard import (
    DashboardActiveFocusSession,
    DashboardCharacter,
    DashboardCriticalTask,
    DashboardExploration,
    DashboardFocusResources,
    DashboardFocusToday,
    DashboardHabitsToday,
    DashboardInProgressTask,
    DashboardNextArea,
    DashboardOnboarding,
    DashboardPendingHabit,
    DashboardPendingRewards,
    DashboardResponse,
    DashboardRewardsBreakdown,
    DashboardSleepLast,
    DashboardTagSummary,
    DashboardTasksToday,
    DashboardWorkoutLast,
)

log = logging.getLogger(__name__)

# ── Exploration constants (mirrored from services/exploration.py) ──────────────

_DIFFICULTY_MODIFIER: dict[str, float] = {
    "easy": 0.9,
    "medium": 0.7,
    "hard": 0.5,
    "extreme": 0.3,
}

_EXPLORATION_AREAS: list[dict] = [
    {
        "name": "Abandoned Suburb",
        "difficulty": "easy",
        "min_character_level": 1,
        "min_skill_requirements": None,
    },
    {
        "name": "Collapsed Highway",
        "difficulty": "easy",
        "min_character_level": 1,
        "min_skill_requirements": None,
    },
    {
        "name": "Overrun Supermarket",
        "difficulty": "medium",
        "min_character_level": 3,
        "min_skill_requirements": {"survival": 2},
    },
    {
        "name": "Flooded Hospital",
        "difficulty": "medium",
        "min_character_level": 4,
        "min_skill_requirements": {"resilience": 2},
    },
    {
        "name": "Military Checkpoint",
        "difficulty": "hard",
        "min_character_level": 6,
        "min_skill_requirements": {"strength": 3, "agility": 2},
    },
    {
        "name": "Downtown Ruins",
        "difficulty": "hard",
        "min_character_level": 7,
        "min_skill_requirements": {"endurance": 3},
    },
    {
        "name": "Underground Bunker",
        "difficulty": "extreme",
        "min_character_level": 10,
        "min_skill_requirements": {"focus": 4, "survival": 4},
    },
    {
        "name": "The Dead Zone",
        "difficulty": "extreme",
        "min_character_level": 15,
        "min_skill_requirements": {"strength": 5, "resilience": 5, "agility": 5},
    },
]

# ── Shared utilities ───────────────────────────────────────────────────────────


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _today_bounds() -> tuple[str, str]:
    """Return (today_start_iso, tomorrow_start_iso) at UTC midnight."""
    now = _utc_now().replace(hour=0, minute=0, second=0, microsecond=0)
    return now.isoformat(), (now + timedelta(days=1)).isoformat()


def _parse_dt(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _flatten_tags(row: dict) -> list[DashboardTagSummary]:
    return [
        DashboardTagSummary(**item["tags"])
        for item in row.pop("task_tags", [])
        if item.get("tags")
    ]


def _success_chance(difficulty: str, impact_score: int) -> float:
    base = _DIFFICULTY_MODIFIER.get(difficulty, 0.5)
    bonus = min(impact_score * 0.01, 0.40)
    return round(base + bonus, 4)


def _area_is_unlocked(area: dict, char_level: int, skills: dict[str, int]) -> bool:
    if char_level < area["min_character_level"]:
        return False
    for skill_name, min_lvl in (area["min_skill_requirements"] or {}).items():
        if skills.get(skill_name, 0) < min_lvl:
            return False
    return True


# ── Safe gather wrapper ───────────────────────────────────────────────────────


async def _safe_gather(coro, default, label: str):
    """
    Awaits `coro` and returns its result. On any exception, logs the error and
    returns `default` so the rest of the dashboard is unaffected.
    """
    try:
        return await coro
    except Exception as exc:
        log.error("Dashboard sub-query '%s' failed: %s", label, exc, exc_info=True)
        return default


# ── Sub-query: character ───────────────────────────────────────────────────────


def _sync_fetch_character(user_id: str) -> DashboardCharacter | None:
    sb = get_supabase()

    char_res = (
        sb.table("characters").select("*").eq("user_id", user_id).limit(1).execute()
    )
    if not char_res.data:
        return None
    char = char_res.data[0]
    cid: str = char["id"]

    stats_res = (
        sb.table("character_stats")
        .select("*")
        .eq("character_id", cid)
        .limit(1)
        .execute()
    )
    if not stats_res.data:
        return None
    stats = stats_res.data[0]

    level: int = char.get("level", 1)
    xp: int = char.get("experience_points", 0)
    xp_needed: int = max(1, level * 100)
    xp_pct = round(min(100.0, (xp / xp_needed) * 100), 1)

    return DashboardCharacter(
        id=cid,
        name=char.get("name"),
        level=level,
        experience_points=xp,
        experience_to_next_level=xp_needed,
        xp_progress_pct=xp_pct,
        is_alive=char.get("is_alive", True),
        death_count=char.get("death_count", 0),
        health=stats["health"],
        max_health=stats["max_health"],
        energy=stats["energy"],
        max_energy=stats["max_energy"],
        hunger=stats["hunger"],
        hydration=stats["hydration"],
        last_fed_at=_parse_dt(stats.get("last_fed_at")),
        last_hydrated_at=_parse_dt(stats.get("last_hydrated_at")),
        hunger_critical=stats["hunger"] < 20,
        hydration_critical=stats["hydration"] < 20,
        health_critical=stats["health"] < 25,
        energy_low=stats["energy"] < 30,
    )


# ── Sub-query: tasks_today ─────────────────────────────────────────────────────


def _sync_fetch_tasks_today(user_id: str) -> DashboardTasksToday:
    sb = get_supabase()
    today_start, tomorrow_start = _today_bounds()
    now_iso = _utc_now().isoformat()

    # total_pending: pending + in_progress
    pending_res = (
        sb.table("tasks")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .in_("status", ["pending", "in_progress"])
        .execute()
    )
    total_pending: int = pending_res.count or 0

    # completed_today: completed_at within today UTC
    completed_res = (
        sb.table("tasks")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .gte("completed_at", today_start)
        .lt("completed_at", tomorrow_start)
        .execute()
    )
    completed_today: int = completed_res.count or 0

    # overdue_count: pending/in_progress with due_date < now
    overdue_res = (
        sb.table("tasks")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .in_("status", ["pending", "in_progress"])
        .not_.is_("due_date", "null")
        .lt("due_date", now_iso)
        .execute()
    )
    overdue_count: int = overdue_res.count or 0

    # in_progress task with full detail (tags)
    ip_res = (
        sb.table("tasks")
        .select("*, task_tags(tags(id, name, color))")
        .eq("user_id", user_id)
        .eq("status", "in_progress")
        .limit(1)
        .execute()
    )
    in_progress_task: DashboardInProgressTask | None = None
    if ip_res.data:
        row = ip_res.data[0]
        tags = _flatten_tags(row)
        in_progress_task = DashboardInProgressTask(
            **{k: v for k, v in row.items() if k not in ("task_tags",)},
            tags=tags,
        )

    # critical_pending: top 3 critical/high pending tasks, sorted by due_date
    crit_res = (
        sb.table("tasks")
        .select("id, title, priority, due_date, estimated_adventure_impact")
        .eq("user_id", user_id)
        .in_("status", ["pending", "in_progress"])
        .in_("priority", ["critical", "high"])
        .execute()
    )
    _priority_rank = {"critical": 2, "high": 1}
    critical_rows = sorted(
        crit_res.data or [],
        key=lambda t: (
            -_priority_rank.get(t.get("priority", "high"), 0),
            t.get("due_date") or "9999-99-99",
        ),
    )[:3]
    critical_pending = [
        DashboardCriticalTask(
            id=r["id"],
            title=r["title"],
            priority=r["priority"],
            due_date=_parse_dt(r.get("due_date")),
            estimated_adventure_impact=r.get("estimated_adventure_impact"),
        )
        for r in critical_rows
    ]

    # active_focus_session: any focus session with ended_at IS NULL
    focus_res = (
        sb.table("focus_sessions")
        .select("id, task_id, type, started_at")
        .eq("user_id", user_id)
        .filter("ended_at", "is", "null")
        .limit(1)
        .execute()
    )
    active_focus: DashboardActiveFocusSession | None = None
    if focus_res.data:
        fs = focus_res.data[0]
        active_focus = DashboardActiveFocusSession(
            id=fs["id"],
            task_id=fs.get("task_id"),
            type=fs["type"],
            started_at=_parse_dt(fs["started_at"]),
        )

    return DashboardTasksToday(
        total_pending=total_pending,
        completed_today=completed_today,
        overdue_count=overdue_count,
        in_progress=in_progress_task,
        critical_pending=critical_pending,
        active_focus_session=active_focus,
    )


# ── Sub-query: habits_today ────────────────────────────────────────────────────


def _sync_fetch_habits_today(user_id: str) -> DashboardHabitsToday:
    sb = get_supabase()
    today_str = _utc_now().date().isoformat()

    # All active habits
    habits_res = (
        sb.table("habits")
        .select("id, name, nature, color, icon")
        .eq("user_id", user_id)
        .eq("is_active", True)
        .order("name")
        .execute()
    )
    active_habits: list[dict] = habits_res.data or []
    total_active = len(active_habits)

    if total_active == 0:
        return DashboardHabitsToday(
            total_active_habits=0,
            logged_today=0,
            completed_today=0,
            pending_today=[],
            completion_rate_today=0.0,
        )

    habit_ids = [h["id"] for h in active_habits]

    # Habit logs for today
    logs_res = (
        sb.table("habit_logs")
        .select("habit_id, was_completed")
        .eq("user_id", user_id)
        .eq("logged_at", today_str)
        .in_("habit_id", habit_ids)
        .execute()
    )
    log_by_habit: dict[str, dict] = {
        lg["habit_id"]: lg for lg in (logs_res.data or [])
    }

    logged_today = len(log_by_habit)
    completed_today = sum(
        1 for lg in log_by_habit.values() if lg.get("was_completed")
    )
    completion_rate = (
        round(completed_today / total_active * 100, 1) if total_active else 0.0
    )

    pending_habits = [
        DashboardPendingHabit(
            id=h["id"],
            name=h["name"],
            nature=h["nature"],
            color=h.get("color"),
            icon=h.get("icon"),
        )
        for h in active_habits
        if h["id"] not in log_by_habit
    ][:5]

    return DashboardHabitsToday(
        total_active_habits=total_active,
        logged_today=logged_today,
        completed_today=completed_today,
        pending_today=pending_habits,
        completion_rate_today=completion_rate,
    )


# ── Sub-query: focus_today ─────────────────────────────────────────────────────


def _sync_fetch_focus_today(user_id: str) -> DashboardFocusToday:
    sb = get_supabase()
    today_start, tomorrow_start = _today_bounds()

    sessions_res = (
        sb.table("focus_sessions")
        .select("duration_seconds, was_completed, resources_earned")
        .eq("user_id", user_id)
        .gte("started_at", today_start)
        .lt("started_at", tomorrow_start)
        .execute()
    )
    sessions: list[dict] = sessions_res.data or []

    total_seconds = sum((s.get("duration_seconds") or 0) for s in sessions)
    completed_count = sum(1 for s in sessions if s.get("was_completed"))

    water = food = materials = 0
    for s in sessions:
        r: dict = s.get("resources_earned") or {}
        water += int(r.get("water") or 0)
        food += int(r.get("food") or 0)
        materials += int(r.get("materials") or 0)

    return DashboardFocusToday(
        sessions_today=len(sessions),
        total_minutes_today=round(total_seconds / 60),
        completed_sessions_today=completed_count,
        resources_earned_today=DashboardFocusResources(
            water=water, food=food, materials=materials
        ),
    )


# ── Sub-query: sleep_last ──────────────────────────────────────────────────────


def _sync_fetch_sleep_last(user_id: str) -> DashboardSleepLast | None:
    sb = get_supabase()

    res = (
        sb.table("sleep_sessions")
        .select(
            "external_date, total_sleep_hours, total_sleep_minutes, "
            "rem_hours, deep_hours, core_hours, awake_hours, "
            "sleep_quality, sleep_start, sleep_end"
        )
        .eq("user_id", user_id)
        .order("external_date", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None

    row = res.data[0]
    today = _utc_now().date()
    try:
        from datetime import date
        session_date = date.fromisoformat(row["external_date"][:10])
        days_since = (today - session_date).days
    except (ValueError, TypeError):
        days_since = 0

    return DashboardSleepLast(
        external_date=row["external_date"],
        total_sleep_hours=row.get("total_sleep_hours"),
        total_sleep_minutes=row.get("total_sleep_minutes"),
        rem_hours=row.get("rem_hours"),
        deep_hours=row.get("deep_hours"),
        core_hours=row.get("core_hours"),
        awake_hours=row.get("awake_hours"),
        sleep_quality=row.get("sleep_quality"),
        sleep_start=_parse_dt(row.get("sleep_start")),
        sleep_end=_parse_dt(row.get("sleep_end")),
        days_since=max(0, days_since),
    )


# ── Sub-query: workout_last ────────────────────────────────────────────────────


def _sync_fetch_workout_last(user_id: str) -> DashboardWorkoutLast | None:
    sb = get_supabase()

    res = (
        sb.table("workout_sessions")
        .select(
            "name, started_at, duration_seconds, distance_km, "
            "active_energy_kcal, avg_heart_rate, effort_level"
        )
        .eq("user_id", user_id)
        .order("started_at", desc=True)
        .limit(1)
        .execute()
    )
    if not res.data:
        return None

    row = res.data[0]
    today = _utc_now().date()
    started_dt = _parse_dt(row.get("started_at"))
    days_since = 0
    if started_dt:
        days_since = max(0, (today - started_dt.date()).days)

    return DashboardWorkoutLast(
        name=row.get("name"),
        started_at=started_dt,
        duration_seconds=row.get("duration_seconds"),
        distance_km=row.get("distance_km"),
        active_energy_kcal=row.get("active_energy_kcal"),
        avg_heart_rate=row.get("avg_heart_rate"),
        effort_level=row.get("effort_level"),
        days_since=days_since,
    )


# ── Sub-query: pending_rewards ─────────────────────────────────────────────────


def _sync_fetch_pending_rewards(user_id: str) -> DashboardPendingRewards:
    sb = get_supabase()

    char_res = (
        sb.table("characters")
        .select("id")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not char_res.data:
        return DashboardPendingRewards(
            total_pending=0,
            has_unprocessed=False,
            breakdown=DashboardRewardsBreakdown(),
            estimated_health_delta=0,
            estimated_energy_delta=0,
        )

    cid: str = char_res.data[0]["id"]

    rewards_res = (
        sb.table("pending_rewards")
        .select("source_type, health_delta, energy_delta")
        .eq("character_id", cid)
        .eq("is_processed", False)
        .execute()
    )
    rewards: list[dict] = rewards_res.data or []

    breakdown_counts: dict[str, int] = {
        "focus_session": 0,
        "habit_log": 0,
        "workout_session": 0,
        "sleep_session": 0,
    }
    total_health_delta = 0
    total_energy_delta = 0

    for r in rewards:
        src = r.get("source_type", "")
        if src in breakdown_counts:
            breakdown_counts[src] += 1
        total_health_delta += int(r.get("health_delta") or 0)
        total_energy_delta += int(r.get("energy_delta") or 0)

    total = len(rewards)
    return DashboardPendingRewards(
        total_pending=total,
        has_unprocessed=total > 0,
        breakdown=DashboardRewardsBreakdown(**breakdown_counts),
        estimated_health_delta=total_health_delta,
        estimated_energy_delta=total_energy_delta,
    )


# ── Sub-query: exploration ─────────────────────────────────────────────────────


def _sync_fetch_exploration(user_id: str) -> DashboardExploration:
    sb = get_supabase()

    char_res = (
        sb.table("characters")
        .select("id, level, created_at")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    if not char_res.data:
        return DashboardExploration(is_active=False)

    char = char_res.data[0]
    cid: str = char["id"]
    char_level: int = char.get("level", 1)

    # Build skills map for area unlock checks
    skills_res = (
        sb.table("character_skills")
        .select("skill_name, level")
        .eq("character_id", cid)
        .execute()
    )
    skills_map: dict[str, int] = {
        row["skill_name"]: row["level"] for row in (skills_res.data or [])
    }

    # Compute live adventure impact score:
    # tasks completed since the last ended exploration (or character creation)
    last_ended_res = (
        sb.table("explorations")
        .select("ended_at")
        .eq("character_id", cid)
        .not_.is_("ended_at", "null")
        .order("ended_at", desc=True)
        .limit(1)
        .execute()
    )
    if last_ended_res.data and last_ended_res.data[0].get("ended_at"):
        since_iso = last_ended_res.data[0]["ended_at"]
    else:
        since_iso = char.get("created_at", "1970-01-01T00:00:00+00:00")

    impact_res = (
        sb.table("tasks")
        .select("estimated_adventure_impact")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .gte("completed_at", since_iso)
        .not_.is_("estimated_adventure_impact", "null")
        .execute()
    )
    current_impact = sum(
        int(r.get("estimated_adventure_impact") or 0) for r in (impact_res.data or [])
    )

    # Compute next_area_estimate: best unlocked area
    next_area: DashboardNextArea | None = None
    best_chance = -1.0
    for area in _EXPLORATION_AREAS:
        if _area_is_unlocked(area, char_level, skills_map):
            chance = _success_chance(area["difficulty"], current_impact)
            if chance > best_chance:
                best_chance = chance
                next_area = DashboardNextArea(
                    area_name=area["name"],
                    difficulty=area["difficulty"],
                    success_chance=chance,
                )

    # Active exploration check
    active_res = (
        sb.table("explorations")
        .select("area_name, started_at, adventure_impact_score, status")
        .eq("character_id", cid)
        .eq("status", "in_progress")
        .limit(1)
        .execute()
    )
    if active_res.data:
        ae = active_res.data[0]
        return DashboardExploration(
            is_active=True,
            area_name=ae["area_name"],
            started_at=_parse_dt(ae.get("started_at")),
            current_impact_score=current_impact,
            next_area_estimate=next_area,
        )

    # Last completed/failed exploration
    last_res = (
        sb.table("explorations")
        .select("area_name, was_successful, ended_at, resources_found")
        .eq("character_id", cid)
        .not_.is_("ended_at", "null")
        .order("ended_at", desc=True)
        .limit(1)
        .execute()
    )
    if last_res.data:
        le = last_res.data[0]
        return DashboardExploration(
            is_active=False,
            area_name=le.get("area_name"),
            was_successful=le.get("was_successful"),
            ended_at=_parse_dt(le.get("ended_at")),
            resources_found=le.get("resources_found"),
            next_area_estimate=next_area,
        )

    return DashboardExploration(is_active=False, next_area_estimate=next_area)


# ── Sub-query: onboarding ──────────────────────────────────────────────────────


def _sync_fetch_onboarding(user_id: str) -> DashboardOnboarding:
    sb = get_supabase()

    profile_res = (
        sb.table("profiles")
        .select("onboarding_completed, avatar_type_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if not profile_res.data:
        return DashboardOnboarding(
            is_completed=False,
            avatar_assigned=False,
            character_created=False,
        )

    profile = profile_res.data[0]
    is_completed: bool = bool(profile.get("onboarding_completed", False))
    avatar_assigned: bool = profile.get("avatar_type_id") is not None

    char_res = (
        sb.table("characters")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .limit(1)
        .execute()
    )
    character_created: bool = bool(char_res.data)

    return DashboardOnboarding(
        is_completed=is_completed,
        avatar_assigned=avatar_assigned,
        character_created=character_created,
    )


# ── Default values for failed sub-queries ─────────────────────────────────────


def _default_tasks_today() -> DashboardTasksToday:
    return DashboardTasksToday(
        total_pending=0,
        completed_today=0,
        overdue_count=0,
        in_progress=None,
        critical_pending=[],
        active_focus_session=None,
    )


def _default_habits_today() -> DashboardHabitsToday:
    return DashboardHabitsToday(
        total_active_habits=0,
        logged_today=0,
        completed_today=0,
        pending_today=[],
        completion_rate_today=0.0,
    )


def _default_focus_today() -> DashboardFocusToday:
    return DashboardFocusToday(
        sessions_today=0,
        total_minutes_today=0,
        completed_sessions_today=0,
        resources_earned_today=DashboardFocusResources(),
    )


def _default_pending_rewards() -> DashboardPendingRewards:
    return DashboardPendingRewards(
        total_pending=0,
        has_unprocessed=False,
        breakdown=DashboardRewardsBreakdown(),
        estimated_health_delta=0,
        estimated_energy_delta=0,
    )


def _default_exploration() -> DashboardExploration:
    return DashboardExploration(is_active=False)


def _default_onboarding() -> DashboardOnboarding:
    return DashboardOnboarding(
        is_completed=False,
        avatar_assigned=False,
        character_created=False,
    )


# ── Public entry point ─────────────────────────────────────────────────────────


async def get_dashboard(user_id: str) -> DashboardResponse:
    """
    Dispatch all nine sub-queries to the thread-pool concurrently via
    asyncio.gather(). Each coroutine is wrapped in _safe_gather() so a single
    failing query cannot cascade into a total dashboard failure.
    """
    (
        character,
        tasks_today,
        habits_today,
        focus_today,
        sleep_last,
        workout_last,
        pending_rewards,
        exploration,
        onboarding,
    ) = await asyncio.gather(
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_character, user_id)),
            None,
            "character",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_tasks_today, user_id)),
            _default_tasks_today(),
            "tasks_today",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_habits_today, user_id)),
            _default_habits_today(),
            "habits_today",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_focus_today, user_id)),
            _default_focus_today(),
            "focus_today",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_sleep_last, user_id)),
            None,
            "sleep_last",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_workout_last, user_id)),
            None,
            "workout_last",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_pending_rewards, user_id)),
            _default_pending_rewards(),
            "pending_rewards",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_exploration, user_id)),
            _default_exploration(),
            "exploration",
        ),
        _safe_gather(
            asyncio.to_thread(partial(_sync_fetch_onboarding, user_id)),
            _default_onboarding(),
            "onboarding",
        ),
    )

    return DashboardResponse(
        character=character,
        tasks_today=tasks_today,
        habits_today=habits_today,
        focus_today=focus_today,
        sleep_last=sleep_last,
        workout_last=workout_last,
        pending_rewards=pending_rewards,
        exploration=exploration,
        onboarding=onboarding,
    )
