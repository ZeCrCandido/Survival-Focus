from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.supabase_client import get_supabase
from app.parsers.apple_health import ParsedWorkout
from app.schemas.workouts import WorkoutGoalCreate, WorkoutGoalUpdate, WorkoutNoteCreate, WorkoutNoteUpdate


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# All session metric columns — used in every SELECT to avoid SELECT *.
_SESSION_SELECT = (
    "id, user_id, external_id, name, source, started_at, ended_at, "
    "duration_seconds, distance_km, active_energy_kcal, avg_heart_rate, "
    "max_heart_rate, min_heart_rate, avg_speed_kmh, step_cadence, "
    "total_steps, temperature_celsius, humidity_percent, elevation_up_meters, "
    "intensity, effort_level, character_impact, is_processed, processed_at, "
    "created_at, updated_at"
)

# Detail view: session columns + workout_notes embed.
_SESSION_DETAIL_SELECT = _SESSION_SELECT + (
    ", workout_notes(id, user_id, workout_session_id, content, created_at, updated_at)"
)

# Base impact (health, energy) per 10-minute block, keyed by effort_level.
_IMPACT_PER_10_MIN: dict[str, dict[str, int]] = {
    "light":    {"health": 1, "energy": 1},
    "moderate": {"health": 2, "energy": 1},
    "hard":     {"health": 3, "energy": 2},
    "max":      {"health": 4, "energy": 2},
}

# Columns allowed in ORDER BY — prevents injection via sort_by parameter.
_SORTABLE_COLUMNS = frozenset(
    {"started_at", "duration_seconds", "distance_km", "active_energy_kcal"}
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _date_from_ts(ts: Any) -> date | None:
    """Extract the date part from an ISO timestamptz string. Returns None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts)).date()
    except (ValueError, TypeError):
        return None


def _calculate_character_impact(
    effort_level: str | None, duration_seconds: int
) -> dict:
    """
    Compute { health, energy } for a workout.

    Formula: base_per_10_min × number_of_10_minute_blocks, minimum 1 each.
    A 27-minute hard session → 2.7 blocks → health = round(3 × 2.7) = 8, energy = round(2 × 2.7) = 5.
    """
    base = _IMPACT_PER_10_MIN.get(effort_level or "light", {"health": 1, "energy": 1})
    blocks = duration_seconds / 600  # 600 seconds = 10 minutes
    return {
        "health": max(1, round(base["health"] * blocks)),
        "energy": max(1, round(base["energy"] * blocks)),
    }


def _flatten_detail(row: dict) -> dict:
    """
    PostgREST returns the workout_notes embed under the key "workout_notes".
    Rename it to "notes" so it matches WorkoutSessionDetailResponse.
    """
    row["notes"] = row.pop("workout_notes", None) or []
    return row


def _require_session(supabase, user_id: str, session_id: str) -> None:
    """Raise 404 if the session does not exist or does not belong to the user."""
    resp = _execute(
        supabase.table("workout_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Workout session not found.", 404)


# ── Import ────────────────────────────────────────────────────────────────────


def import_workouts(user_id: str, parsed: list[ParsedWorkout]) -> dict:
    """
    Persist a list of parsed workouts, skipping any whose external_id has
    already been imported for this user.

    Duplicate detection is done in a single batch SELECT before the insert
    loop — no N+1 queries.  Each individual insert is wrapped in try/except
    so one bad row never aborts the remaining batch.

    Returns a summary dict consumed by the router to build WorkoutImportSummary.
    """
    supabase = get_supabase()

    if not parsed:
        return {
            "total_in_file":      0,
            "imported":           0,
            "skipped_duplicates": 0,
            "failed":             0,
            "sessions":           [],
        }

    # ── Batch duplicate check ──────────────────────────────────────────────────
    ext_ids = [pw.external_id for pw in parsed if pw.external_id]
    existing_ext_ids: set[str] = set()
    if ext_ids:
        resp = _execute(
            supabase.table("workout_sessions")
            .select("external_id")
            .eq("user_id", user_id)
            .in_("external_id", ext_ids)
        )
        existing_ext_ids = {row["external_id"] for row in resp.data}

    imported:           int        = 0
    skipped_duplicates: int        = 0
    failed:             int        = 0
    inserted_sessions:  list[dict] = []

    for pw in parsed:
        if pw.external_id and pw.external_id in existing_ext_ids:
            skipped_duplicates += 1
            continue

        try:
            impact = _calculate_character_impact(pw.effort_level, pw.duration_seconds)

            payload: dict = {
                "user_id":              user_id,
                # Preserve empty string as None — the unique partial index
                # only covers non-null external_ids.
                "external_id":          pw.external_id or None,
                "name":                 pw.name,
                "source":               pw.source,
                "started_at":           pw.started_at.isoformat(),
                "ended_at":             pw.ended_at.isoformat(),
                "duration_seconds":     pw.duration_seconds,
                "distance_km":          pw.distance_km,
                "active_energy_kcal":   pw.active_energy_kcal,
                "avg_heart_rate":       pw.avg_heart_rate,
                "max_heart_rate":       pw.max_heart_rate,
                "min_heart_rate":       pw.min_heart_rate,
                "avg_speed_kmh":        pw.avg_speed_kmh,
                "step_cadence":         pw.step_cadence,
                "total_steps":          pw.total_steps,
                "temperature_celsius":  pw.temperature_celsius,
                "humidity_percent":     pw.humidity_percent,
                "elevation_up_meters":  pw.elevation_up_meters,
                "intensity":            pw.intensity,
                "effort_level":         pw.effort_level,
                "character_impact":     impact,
                "is_processed":         False,
                "raw_data":             pw.raw_data,
            }

            resp = supabase.table("workout_sessions").insert(payload).execute()
            inserted_sessions.append(resp.data[0])
            imported += 1

        except Exception:
            failed += 1
            continue

    return {
        "total_in_file":      len(parsed),
        "imported":           imported,
        "skipped_duplicates": skipped_duplicates,
        "failed":             failed,
        "sessions":           inserted_sessions,
    }


# ── Sessions ──────────────────────────────────────────────────────────────────


def list_workouts(
    user_id: str,
    *,
    from_date:    str | None = None,
    to_date:      str | None = None,
    effort_level: str | None = None,
    sort_by:      str        = "started_at",
    order:        str        = "desc",
    limit:        int        = 20,
    offset:       int        = 0,
) -> tuple[list[dict], int]:
    supabase = get_supabase()

    query = (
        supabase.table("workout_sessions")
        .select(_SESSION_SELECT, count="exact")
        .eq("user_id", user_id)
    )

    if from_date:
        query = query.gte("started_at", from_date)
    if to_date:
        # Append end-of-day so the `to` date is fully inclusive.
        query = query.lte("started_at", to_date + "T23:59:59+00:00")
    if effort_level:
        query = query.eq("effort_level", effort_level)

    safe_sort = sort_by if sort_by in _SORTABLE_COLUMNS else "started_at"
    query = (
        query
        .order(safe_sort, desc=(order == "desc"))
        .range(offset, offset + limit - 1)
    )

    resp  = _execute(query)
    total = resp.count if resp.count is not None else len(resp.data)
    return resp.data, total


def get_workout(user_id: str, session_id: str) -> dict:
    resp = _execute(
        get_supabase()
        .table("workout_sessions")
        .select(_SESSION_DETAIL_SELECT)
        .eq("id", session_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Workout session not found.", 404)
    return _flatten_detail(resp.data[0])


def delete_workout(user_id: str, session_id: str) -> None:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)
    # workout_notes are removed automatically by the DB CASCADE.
    _execute(
        supabase.table("workout_sessions")
        .delete()
        .eq("id", session_id)
        .eq("user_id", user_id)
    )


# ── Goals ─────────────────────────────────────────────────────────────────────


def list_goals(user_id: str) -> list[dict]:
    return _execute(
        get_supabase()
        .table("workout_goals")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
    ).data


def create_goal(user_id: str, body: WorkoutGoalCreate) -> dict:
    try:
        resp = get_supabase().table("workout_goals").insert({
            "user_id":      user_id,
            "goal_type":    body.goal_type.value,
            "period":       body.period.value,
            "target_value": body.target_value,
        }).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ServiceError(
                f"A {body.period.value} '{body.goal_type.value}' goal already exists.", 409
            )
        raise ServiceError(f"Database error: {exc}", 500)
    return resp.data[0]


def update_goal(user_id: str, goal_id: str, body: WorkoutGoalUpdate) -> dict:
    supabase = get_supabase()
    _execute(
        supabase.table("workout_goals")
        .select("id")
        .eq("id", goal_id)
        .eq("user_id", user_id)
    ).data or _raise_404("Workout goal not found.")

    resp = _execute(
        supabase.table("workout_goals")
        .update({"target_value": body.target_value})
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Workout goal not found.", 404)
    return resp.data[0]


def delete_goal(user_id: str, goal_id: str) -> None:
    supabase = get_supabase()
    exists = _execute(
        supabase.table("workout_goals")
        .select("id")
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Workout goal not found.", 404)
    _execute(
        supabase.table("workout_goals")
        .delete()
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )


def _raise_404(msg: str) -> None:
    raise ServiceError(msg, 404)


# ── Notes ─────────────────────────────────────────────────────────────────────


def add_note(user_id: str, session_id: str, body: WorkoutNoteCreate) -> dict:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)
    try:
        resp = supabase.table("workout_notes").insert({
            "user_id":            user_id,
            "workout_session_id": session_id,
            "content":            body.content,
        }).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to add note: {exc}", 500)
    return resp.data[0]


def update_note(
    user_id: str, session_id: str, note_id: str, body: WorkoutNoteUpdate
) -> dict:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)

    resp = _execute(
        supabase.table("workout_notes")
        .update({"content": body.content})
        .eq("id", note_id)
        .eq("workout_session_id", session_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Note not found.", 404)
    return resp.data[0]


def delete_note(user_id: str, session_id: str, note_id: str) -> None:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)

    exists = _execute(
        supabase.table("workout_notes")
        .select("id")
        .eq("id", note_id)
        .eq("workout_session_id", session_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Note not found.", 404)

    _execute(
        supabase.table("workout_notes")
        .delete()
        .eq("id", note_id)
        .eq("workout_session_id", session_id)
        .eq("user_id", user_id)
    )


# ── Stats ─────────────────────────────────────────────────────────────────────


def _weekly_summary(sessions: list[dict], weeks: int = 8) -> list[dict]:
    """
    Group sessions into Mon–Sun calendar weeks and aggregate per week.
    Returns a list of `weeks` entries, oldest week first.
    """
    today      = _today_utc()
    week_start = today - timedelta(days=today.weekday())  # most recent Monday

    result: list[dict] = []
    for i in range(weeks - 1, -1, -1):  # iterate oldest → newest
        wk_start  = week_start - timedelta(weeks=i)
        wk_end    = wk_start + timedelta(days=6)
        wk_sessions = [
            s for s in sessions
            if (d := _date_from_ts(s.get("started_at"))) is not None
            and wk_start <= d <= wk_end
        ]
        result.append({
            "week_start":               wk_start.isoformat(),
            "sessions":                 len(wk_sessions),
            "total_distance_km":        round(
                sum(float(s.get("distance_km") or 0) for s in wk_sessions), 3
            ),
            "total_active_energy_kcal": round(
                sum(float(s.get("active_energy_kcal") or 0) for s in wk_sessions), 2
            ),
        })
    return result


def get_stats(user_id: str) -> dict:
    """
    Aggregate lifetime workout statistics.
    All computation is done in Python — acceptable at personal-app scale
    where session counts are in the hundreds, not millions.
    """
    sessions = _execute(
        get_supabase()
        .table("workout_sessions")
        .select(
            "duration_seconds, distance_km, active_energy_kcal, "
            "avg_heart_rate, total_steps, effort_level, name, started_at"
        )
        .eq("user_id", user_id)
        .order("started_at", desc=False)
    ).data

    if not sessions:
        return _empty_stats()

    total_distance_km   = sum(float(s.get("distance_km") or 0) for s in sessions)
    total_energy_kcal   = sum(float(s.get("active_energy_kcal") or 0) for s in sessions)
    total_duration_secs = sum(int(s.get("duration_seconds") or 0) for s in sessions)
    total_steps         = sum(int(s.get("total_steps") or 0) for s in sessions)

    hr_values = [float(s["avg_heart_rate"]) for s in sessions if s.get("avg_heart_rate")]
    avg_hr    = round(sum(hr_values) / len(hr_values), 2) if hr_values else None

    effort_breakdown: dict[str, int] = {
        "light": 0, "moderate": 0, "hard": 0, "max": 0, "unknown": 0
    }
    name_counts: dict[str, int] = {}
    for s in sessions:
        el = s.get("effort_level")
        effort_breakdown[el if el in effort_breakdown else "unknown"] += 1
        name_counts[s.get("name") or "Unknown"] = (
            name_counts.get(s.get("name") or "Unknown", 0) + 1
        )

    most_frequent = max(name_counts, key=lambda k: name_counts[k]) if name_counts else None

    return {
        "total_sessions":           len(sessions),
        "total_distance_km":        round(total_distance_km, 3),
        "total_active_energy_kcal": round(total_energy_kcal, 2),
        "total_duration_minutes":   round(total_duration_secs / 60, 1),
        "total_steps":              total_steps,
        "avg_heart_rate":           avg_hr,
        "effort_breakdown":         effort_breakdown,
        "most_frequent_type":       most_frequent,
        "weekly_summary":           _weekly_summary(sessions),
    }


def _empty_stats() -> dict:
    return {
        "total_sessions":           0,
        "total_distance_km":        0.0,
        "total_active_energy_kcal": 0.0,
        "total_duration_minutes":   0.0,
        "total_steps":              0,
        "avg_heart_rate":           None,
        "effort_breakdown":         {
            "light": 0, "moderate": 0, "hard": 0, "max": 0, "unknown": 0
        },
        "most_frequent_type":       None,
        "weekly_summary":           [],
    }


# ── Goals progress ────────────────────────────────────────────────────────────


def get_goals_progress(user_id: str) -> list[dict]:
    """
    For each goal, compute the achieved value within the current period
    (today for daily, this week for weekly, this month for monthly).

    Efficiency: one SELECT to get all goals, one SELECT to get all sessions
    since the earliest period_start across all goals — no per-goal queries.
    """
    supabase = get_supabase()
    today    = _today_utc()

    goals = _execute(
        supabase.table("workout_goals")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
    ).data

    if not goals:
        return []

    # Compute period_start per goal and find the earliest across all goals
    # so we can cover all periods in a single DB query.
    period_starts: dict[str, date] = {}
    for goal in goals:
        p = goal["period"]
        if p == "daily":
            ps = today
        elif p == "weekly":
            ps = today - timedelta(days=today.weekday())   # last Monday
        else:  # monthly
            ps = today.replace(day=1)
        period_starts[goal["id"]] = ps

    earliest = min(period_starts.values())

    sessions = _execute(
        supabase.table("workout_sessions")
        .select("duration_seconds, distance_km, active_energy_kcal, started_at")
        .eq("user_id", user_id)
        .gte("started_at", earliest.isoformat())
    ).data

    results: list[dict] = []
    for goal in goals:
        ps        = period_starts[goal["id"]]
        goal_type = goal["goal_type"]
        target    = float(goal["target_value"])

        # Each goal type only counts sessions on or after its own period_start.
        period_sessions = [
            s for s in sessions
            if (d := _date_from_ts(s.get("started_at"))) is not None and d >= ps
        ]

        if goal_type == "distance_km":
            achieved = sum(float(s.get("distance_km") or 0) for s in period_sessions)
        elif goal_type == "active_energy_kcal":
            achieved = sum(float(s.get("active_energy_kcal") or 0) for s in period_sessions)
        elif goal_type == "duration_minutes":
            achieved = sum(int(s.get("duration_seconds") or 0) for s in period_sessions) / 60
        else:  # session_count
            achieved = float(len(period_sessions))

        progress_pct = (
            min(100.0, round(achieved / target * 100, 1)) if target > 0 else 0.0
        )

        results.append({
            "goal":             goal,
            "current_value":    round(achieved, 2),
            "target_value":     target,
            "progress_percent": progress_pct,
            "is_met":           achieved >= target,
            "period_start":     ps.isoformat(),
        })

    return results
