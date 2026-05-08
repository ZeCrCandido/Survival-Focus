from datetime import datetime, timezone

from app.core.supabase_client import get_supabase
from app.schemas.focus import FocusSessionEnd, FocusSessionStart


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Scoring tables ─────────────────────────────────────────────────────────────

# Resources earned per full minute of focus time.
_BASE_RESOURCES_PER_MINUTE: dict[str, dict[str, float]] = {
    "pomodoro":  {"water": 2.0, "food": 1.0, "materials": 1.0},
    "stopwatch": {"water": 1.0, "food": 1.0, "materials": 0.0},
}

# Flat bonus added on top when was_completed=True.
_COMPLETION_BONUS: dict[str, dict[str, int]] = {
    "pomodoro":  {"water": 5, "food": 3, "materials": 2},
    "stopwatch": {"water": 2, "food": 2, "materials": 1},
}

# XP granted for a fully completed pomodoro session.
_XP_BASE_POMODORO    = 10   # awarded regardless of duration
_XP_PER_MINUTE_POMODORO = 2 # bonus per minute (25-min session → 60 XP total)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _parse_utc(ts: str) -> datetime:
    """Parse an ISO 8601 timestamp from Supabase and ensure it is UTC-aware."""
    dt = datetime.fromisoformat(ts)  # Python 3.11+ handles all ISO 8601 variants
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _calculate_resources(
    session_type: str, duration_seconds: int, was_completed: bool
) -> dict:
    """
    Compute resources earned for a session.
    Base resources scale linearly with duration; a flat bonus is added on completion.
    """
    minutes = duration_seconds / 60
    base = _BASE_RESOURCES_PER_MINUTE[session_type]

    earned = {
        "water":     max(0, round(base["water"]     * minutes)),
        "food":      max(0, round(base["food"]       * minutes)),
        "materials": max(0, round(base["materials"]  * minutes)),
    }

    if was_completed:
        bonus = _COMPLETION_BONUS[session_type]
        earned["water"]     += bonus["water"]
        earned["food"]      += bonus["food"]
        earned["materials"] += bonus["materials"]

    return earned


def _calculate_xp(duration_seconds: int) -> int:
    """XP for a completed pomodoro: flat base + 2 XP per minute of focus."""
    return _XP_BASE_POMODORO + round(_XP_PER_MINUTE_POMODORO * duration_seconds / 60)


# ── Start & end ───────────────────────────────────────────────────────────────


def start_session(user_id: str, body: FocusSessionStart) -> dict:
    supabase = get_supabase()

    # 1. Verify the task exists and belongs to the caller.
    task = _execute(
        supabase.table("tasks")
        .select("id, status")
        .eq("id", str(body.task_id))
        .eq("user_id", user_id)
    )
    if not task.data:
        raise ServiceError("Task not found.", 404)

    # 2. Enforce one-active-session-at-a-time rule.
    active = _execute(
        supabase.table("focus_sessions")
        .select("id")
        .eq("user_id", user_id)
        .filter("ended_at", "is", "null")
    )
    if active.data:
        raise ServiceError(
            "You already have an active focus session. "
            "End it before starting a new one.",
            409,
        )

    # 3. Mark the task in_progress.
    try:
        supabase.table("tasks").update(
            {"status": "in_progress"}
        ).eq("id", str(body.task_id)).eq("user_id", user_id).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to update task status: {exc}", 500)

    # 4. Create the session row (started_at defaults to now() in the DB).
    try:
        resp = supabase.table("focus_sessions").insert({
            "user_id": user_id,
            "task_id": str(body.task_id),
            "type":    body.type.value,
        }).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to create session: {exc}", 500)

    return resp.data[0]


def end_session(user_id: str, session_id: str, body: FocusSessionEnd) -> dict:
    supabase = get_supabase()

    # 1. Fetch the session and confirm ownership.
    session_resp = _execute(
        supabase.table("focus_sessions")
        .select("*")
        .eq("id", session_id)
        .eq("user_id", user_id)
    )
    if not session_resp.data:
        raise ServiceError("Focus session not found.", 404)

    session = session_resp.data[0]

    if session["ended_at"] is not None:
        raise ServiceError("This session has already been ended.", 409)

    # 2. Calculate timing.
    started_at       = _parse_utc(session["started_at"])
    ended_at         = datetime.now(timezone.utc)
    duration_seconds = max(0, int((ended_at - started_at).total_seconds()))

    # 3. Calculate resources earned from duration + completion status.
    session_type = session["type"]
    resources    = _calculate_resources(session_type, duration_seconds, body.was_completed)

    # 4. Attach pending XP reward for completed pomodoro sessions.
    #    Stored inside resources_earned so no extra column is needed.
    #    The character module queries for rows where
    #    resources_earned->pending_rewards->processed = false.
    if body.was_completed and session_type == "pomodoro":
        resources["pending_rewards"] = {
            "xp":       _calculate_xp(duration_seconds),
            "source":   "pomodoro_completed",
            "processed": False,
        }

    # 5. Persist the ended session.
    try:
        resp = supabase.table("focus_sessions").update({
            "ended_at":         ended_at.isoformat(),
            "duration_seconds": duration_seconds,
            "was_completed":    body.was_completed,
            "resources_earned": resources,
        }).eq("id", session_id).eq("user_id", user_id).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to end session: {exc}", 500)

    # 6. Revert task status to pending on abandonment so it re-enters the queue.
    if not body.was_completed:
        try:
            supabase.table("tasks").update(
                {"status": "pending"}
            ).eq("id", session["task_id"]).eq("user_id", user_id).execute()
        except Exception as exc:
            raise ServiceError(f"Session ended but task status could not be reverted: {exc}", 500)

    return resp.data[0]


# ── Queries ───────────────────────────────────────────────────────────────────


def get_active_session(user_id: str) -> dict | None:
    resp = _execute(
        get_supabase()
        .table("focus_sessions")
        .select("*")
        .eq("user_id", user_id)
        .filter("ended_at", "is", "null")
    )
    return resp.data[0] if resp.data else None


def get_history(user_id: str) -> list[dict]:
    resp = _execute(
        get_supabase()
        .table("focus_sessions")
        .select("*")
        .eq("user_id", user_id)
        .filter("ended_at", "not.is", "null")
        .order("started_at", desc=True)
    )
    return resp.data


def get_task_history(user_id: str, task_id: str) -> list[dict]:
    # Verify the task belongs to the caller before exposing its sessions.
    task = _execute(
        get_supabase()
        .table("tasks")
        .select("id")
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not task.data:
        raise ServiceError("Task not found.", 404)

    resp = _execute(
        get_supabase()
        .table("focus_sessions")
        .select("*")
        .eq("task_id", task_id)
        .eq("user_id", user_id)
        .order("started_at", desc=True)
    )
    return resp.data


# ── Stats ─────────────────────────────────────────────────────────────────────


def get_stats(user_id: str) -> dict:
    """
    Aggregates all ended sessions for the user in Python.
    Acceptable for a personal productivity app where session counts
    are in the hundreds, not millions.
    """
    resp = _execute(
        get_supabase()
        .table("focus_sessions")
        .select("type, duration_seconds, was_completed, resources_earned")
        .eq("user_id", user_id)
        .filter("ended_at", "not.is", "null")  # only finished sessions
    )
    sessions = resp.data

    if not sessions:
        return _empty_stats()

    total_sessions    = len(sessions)
    completed         = sum(1 for s in sessions if s["was_completed"])
    abandoned         = total_sessions - completed
    total_seconds     = sum(s.get("duration_seconds") or 0 for s in sessions)
    total_minutes     = round(total_seconds / 60, 1)
    avg_minutes       = round(total_minutes / total_sessions, 1) if total_sessions else 0.0

    # Aggregate resources — skip the nested pending_rewards key.
    total_water = total_food = total_materials = 0
    for s in sessions:
        r = s.get("resources_earned") or {}
        total_water     += r.get("water",     0)
        total_food      += r.get("food",      0)
        total_materials += r.get("materials", 0)

    # Per-type breakdown.
    by_type: dict[str, dict] = {
        "pomodoro":  {"sessions": 0, "minutes": 0.0},
        "stopwatch": {"sessions": 0, "minutes": 0.0},
    }
    for s in sessions:
        t = s.get("type", "stopwatch")
        if t in by_type:
            by_type[t]["sessions"] += 1
            by_type[t]["minutes"]  += round((s.get("duration_seconds") or 0) / 60, 2)

    # Round per-type minutes for clean output.
    for t in by_type:
        by_type[t]["minutes"] = round(by_type[t]["minutes"], 1)

    return {
        "total_sessions":          total_sessions,
        "total_minutes":           total_minutes,
        "completed_sessions":      completed,
        "abandoned_sessions":      abandoned,
        "total_resources":         {
            "water":     total_water,
            "food":      total_food,
            "materials": total_materials,
        },
        "average_session_minutes": avg_minutes,
        "by_type":                 by_type,
    }


def _empty_stats() -> dict:
    return {
        "total_sessions":          0,
        "total_minutes":           0.0,
        "completed_sessions":      0,
        "abandoned_sessions":      0,
        "total_resources":         {"water": 0, "food": 0, "materials": 0},
        "average_session_minutes": 0.0,
        "by_type": {
            "pomodoro":  {"sessions": 0, "minutes": 0.0},
            "stopwatch": {"sessions": 0, "minutes": 0.0},
        },
    }
