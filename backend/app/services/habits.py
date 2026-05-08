from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.supabase_client import get_supabase
from app.schemas.habits import HabitCreate, HabitLogCreate, HabitSkillCreate, HabitUpdate


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


_HABIT_SELECT = (
    "id, user_id, name, description, nature, frequency, "
    "target_value, unit, color, icon, is_active, created_at, updated_at"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _parse_date(d: Any) -> date:
    if isinstance(d, date):
        return d
    return date.fromisoformat(str(d))


# ── Character impact ──────────────────────────────────────────────────────────


def _calculate_character_impact(
    nature: str,
    was_completed: bool,
    skills: list[dict],
) -> dict:
    """
    Compute the character_impact JSONB stored on a habit_log row.

    Skill rewards are embedded as pending_skill_rewards inside character_impact,
    mirroring how focus sessions embed pending_rewards inside resources_earned.
    The character module queries both with:
      WHERE <jsonb_col>->>'pending_skill_rewards'->>'processed' = 'false'
    and marks processed=true after crediting the character sheet.
    """
    if nature == "healthy":
        if was_completed:
            impact: dict = {"health_delta": 2, "energy_delta": 1}
            if skills:
                impact["pending_skill_rewards"] = {
                    "skills":    {s["skill_name"]: s["points_per_completion"] for s in skills},
                    "source":    "habit_healthy_completed",
                    "processed": False,
                }
        else:
            impact = {"health_delta": 0, "energy_delta": -1}
    else:  # harmful
        if was_completed:
            impact = {"health_delta": -3, "energy_delta": -1}
        else:
            impact = {"health_delta": 1, "energy_delta": 1}

    return impact


# ── Streak & stats helpers ────────────────────────────────────────────────────


def _get_current_streak(habit_id: str) -> int:
    resp = _execute(
        get_supabase().rpc("calculate_habit_streak", {"p_habit_id": habit_id})
    )
    return resp.data or 0


def _calculate_longest_streak(logs: list[dict], frequency: str) -> int:
    """Walk completed logs in chronological order to find the all-time best streak."""
    completed_dates = sorted(
        _parse_date(lg["logged_at"]) for lg in logs if lg["was_completed"]
    )
    if not completed_dates:
        return 0

    max_gap = 1 if frequency == "daily" else 7
    current = longest = 1

    for i in range(1, len(completed_dates)):
        delta = (completed_dates[i] - completed_dates[i - 1]).days
        if 0 < delta <= max_gap:
            current += 1
            if current > longest:
                longest = current
        elif delta == 0:
            pass  # duplicate date — same-day double-entry; skip
        else:
            current = 1

    return longest


def _weekly_breakdown(logs: list[dict], weeks: int = 8) -> list[dict]:
    """Return log totals per calendar week (Mon–Sun) for the last `weeks` weeks, oldest first."""
    today      = _today_utc()
    week_start = today - timedelta(days=today.weekday())  # most recent Monday

    result = []
    for i in range(weeks - 1, -1, -1):  # iterate oldest → newest
        wk_start = week_start - timedelta(weeks=i)
        wk_end   = wk_start + timedelta(days=6)
        week_logs = [
            lg for lg in logs
            if wk_start <= _parse_date(lg["logged_at"]) <= wk_end
        ]
        result.append({
            "week_start": wk_start.isoformat(),
            "total":      len(week_logs),
            "completed":  sum(1 for lg in week_logs if lg["was_completed"]),
        })

    return result


# ── Habit CRUD ────────────────────────────────────────────────────────────────


def list_habits(user_id: str) -> list[dict]:
    resp = _execute(
        get_supabase()
        .table("habits")
        .select(_HABIT_SELECT)
        .eq("user_id", user_id)
        .order("created_at", desc=True)
    )
    return resp.data


def get_habit(user_id: str, habit_id: str) -> dict:
    habit_resp = _execute(
        get_supabase()
        .table("habits")
        .select(_HABIT_SELECT)
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not habit_resp.data:
        raise ServiceError("Habit not found.", 404)

    habit  = habit_resp.data[0]
    skills = _get_skills_for_habit(habit_id)
    streak = _get_current_streak(habit_id)
    return {**habit, "skills": skills, "current_streak": streak}


def create_habit(user_id: str, body: HabitCreate) -> dict:
    supabase = get_supabase()

    if body.skills and body.nature.value == "harmful":
        raise ServiceError(
            "Skill mappings are only allowed on healthy habits.", 400
        )

    payload = body.model_dump(exclude={"skills"})
    payload["user_id"]   = user_id
    payload["nature"]    = body.nature.value
    payload["frequency"] = body.frequency.value

    try:
        resp = supabase.table("habits").insert(payload).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ServiceError(f"A habit named '{body.name}' already exists.", 409)
        raise ServiceError(f"Database error: {exc}", 500)

    habit = resp.data[0]

    if body.skills:
        _create_habit_skills(habit["id"], body.skills)

    return {**habit, "skills": _get_skills_for_habit(habit["id"]), "current_streak": 0}


def update_habit(user_id: str, habit_id: str, body: HabitUpdate) -> dict:
    supabase = get_supabase()

    existing = _execute(
        supabase.table("habits")
        .select("id")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not existing.data:
        raise ServiceError("Habit not found.", 404)

    updates: dict = {}
    for field in body.model_fields_set:
        val = getattr(body, field)
        # Normalise Enum members to their string values
        if hasattr(val, "value"):
            val = val.value
        updates[field] = val

    if not updates:
        return get_habit(user_id, habit_id)

    try:
        resp = (
            supabase.table("habits")
            .update(updates)
            .eq("id", habit_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ServiceError("A habit with that name already exists.", 409)
        raise ServiceError(f"Database error: {exc}", 500)

    habit  = resp.data[0]
    skills = _get_skills_for_habit(habit_id)
    streak = _get_current_streak(habit_id)
    return {**habit, "skills": skills, "current_streak": streak}


def archive_habit(user_id: str, habit_id: str) -> dict:
    supabase = get_supabase()

    existing = _execute(
        supabase.table("habits")
        .select("id")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not existing.data:
        raise ServiceError("Habit not found.", 404)

    resp = _execute(
        supabase.table("habits")
        .update({"is_active": False})
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    return resp.data[0]


def delete_habit(user_id: str, habit_id: str) -> None:
    supabase = get_supabase()

    existing = _execute(
        supabase.table("habits")
        .select("id")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not existing.data:
        raise ServiceError("Habit not found.", 404)

    _execute(
        supabase.table("habits")
        .delete()
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )


# ── Habit Logs ────────────────────────────────────────────────────────────────


def list_logs(
    user_id: str, habit_id: str, limit: int = 50, offset: int = 0
) -> list[dict]:
    supabase = get_supabase()

    existing = _execute(
        supabase.table("habits")
        .select("id")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not existing.data:
        raise ServiceError("Habit not found.", 404)

    resp = _execute(
        supabase.table("habit_logs")
        .select("*")
        .eq("habit_id", habit_id)
        .eq("user_id", user_id)
        .order("logged_at", desc=True)
        .range(offset, offset + limit - 1)
    )
    return resp.data


def create_or_update_log(
    user_id: str, habit_id: str, body: HabitLogCreate
) -> dict:
    supabase = get_supabase()

    habit_resp = _execute(
        supabase.table("habits")
        .select("id, nature")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not habit_resp.data:
        raise ServiceError("Habit not found.", 404)

    habit     = habit_resp.data[0]
    logged_at = body.logged_at or _today_utc()

    # Skill rewards only apply to healthy habits
    skills = (
        _get_skills_for_habit(habit_id)
        if habit["nature"] == "healthy"
        else []
    )

    impact = _calculate_character_impact(habit["nature"], body.was_completed, skills)

    payload = {
        "user_id":          user_id,
        "habit_id":         habit_id,
        "logged_at":        logged_at.isoformat() if hasattr(logged_at, "isoformat") else logged_at,
        "was_completed":    body.was_completed,
        "value":            body.value,
        "notes":            body.notes,
        "character_impact": impact,
    }

    try:
        resp = supabase.table("habit_logs").upsert(
            payload, on_conflict="habit_id,logged_at"
        ).execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)

    return resp.data[0]


def get_log_stats(user_id: str, habit_id: str) -> dict:
    supabase = get_supabase()

    habit_resp = _execute(
        supabase.table("habits")
        .select("id, frequency")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not habit_resp.data:
        raise ServiceError("Habit not found.", 404)

    frequency = habit_resp.data[0]["frequency"]

    logs = _execute(
        supabase.table("habit_logs")
        .select("logged_at, was_completed")
        .eq("habit_id", habit_id)
        .eq("user_id", user_id)
        .order("logged_at", desc=False)
    ).data

    total_logs        = len(logs)
    total_completions = sum(1 for lg in logs if lg["was_completed"])
    total_missed      = total_logs - total_completions
    completion_rate   = (
        round(total_completions / total_logs * 100, 1) if total_logs else 0.0
    )

    return {
        "total_logs":        total_logs,
        "total_completions": total_completions,
        "total_missed":      total_missed,
        "current_streak":    _get_current_streak(habit_id),
        "longest_streak":    _calculate_longest_streak(logs, frequency),
        "completion_rate":   completion_rate,
        "weekly_breakdown":  _weekly_breakdown(logs),
    }


def get_today_habits(user_id: str) -> list[dict]:
    supabase = get_supabase()
    today    = _today_utc().isoformat()

    habits = _execute(
        supabase.table("habits")
        .select(_HABIT_SELECT)
        .eq("user_id", user_id)
        .eq("is_active", True)
        .order("created_at", desc=False)
    ).data

    if not habits:
        return []

    logs_resp = _execute(
        supabase.table("habit_logs")
        .select("habit_id, was_completed")
        .eq("user_id", user_id)
        .eq("logged_at", today)
    )
    log_by_habit: dict[str, dict] = {lg["habit_id"]: lg for lg in logs_resp.data}

    result = []
    for habit in habits:
        log = log_by_habit.get(habit["id"])
        result.append({
            "habit":          habit,
            "has_log_today":  log is not None,
            "was_completed":  log["was_completed"] if log else None,
            "current_streak": _get_current_streak(habit["id"]),
        })

    return result


# ── Habit Skills ──────────────────────────────────────────────────────────────


def _get_skills_for_habit(habit_id: str) -> list[dict]:
    resp = _execute(
        get_supabase()
        .table("habit_skills")
        .select("*")
        .eq("habit_id", habit_id)
        .order("created_at", desc=False)
    )
    return resp.data


def _create_habit_skills(habit_id: str, skills: list[HabitSkillCreate]) -> None:
    if not skills:
        return
    rows = [
        {
            "habit_id":             habit_id,
            "skill_name":           s.skill_name,
            "points_per_completion": s.points_per_completion,
        }
        for s in skills
    ]
    try:
        get_supabase().table("habit_skills").insert(rows).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to create skill mappings: {exc}", 500)


def list_skills(user_id: str, habit_id: str) -> list[dict]:
    existing = _execute(
        get_supabase()
        .table("habits")
        .select("id")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not existing.data:
        raise ServiceError("Habit not found.", 404)
    return _get_skills_for_habit(habit_id)


def add_skill(user_id: str, habit_id: str, body: HabitSkillCreate) -> dict:
    supabase = get_supabase()

    habit_resp = _execute(
        supabase.table("habits")
        .select("id, nature")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not habit_resp.data:
        raise ServiceError("Habit not found.", 404)

    if habit_resp.data[0]["nature"] == "harmful":
        raise ServiceError(
            "Skill mappings are only allowed on healthy habits.", 400
        )

    try:
        resp = supabase.table("habit_skills").insert({
            "habit_id":             habit_id,
            "skill_name":           body.skill_name,
            "points_per_completion": body.points_per_completion,
        }).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ServiceError(
                f"Skill '{body.skill_name}' is already mapped to this habit.", 409
            )
        raise ServiceError(f"Database error: {exc}", 500)

    return resp.data[0]


def remove_skill(user_id: str, habit_id: str, skill_id: str) -> None:
    supabase = get_supabase()

    existing = _execute(
        supabase.table("habits")
        .select("id")
        .eq("id", habit_id)
        .eq("user_id", user_id)
    )
    if not existing.data:
        raise ServiceError("Habit not found.", 404)

    skill_resp = _execute(
        supabase.table("habit_skills")
        .select("id")
        .eq("id", skill_id)
        .eq("habit_id", habit_id)
    )
    if not skill_resp.data:
        raise ServiceError("Skill mapping not found.", 404)

    _execute(
        supabase.table("habit_skills")
        .delete()
        .eq("id", skill_id)
        .eq("habit_id", habit_id)
    )
