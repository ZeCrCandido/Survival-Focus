import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.supabase_client import get_supabase
from app.parsers.apple_health_sleep import ParsedSleepEntry
from app.schemas.sleep import SleepGoalCreate, SleepGoalUpdate, SleepNoteCreate, SleepNoteUpdate


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message     = message
        self.status_code = status_code
        super().__init__(message)


# ── Column lists ──────────────────────────────────────────────────────────────

_SESSION_SELECT = (
    "id, user_id, external_date, source, sleep_start, sleep_end, "
    "in_bed_start, in_bed_end, total_sleep_hours, total_sleep_minutes, "
    "rem_hours, rem_minutes, deep_hours, deep_minutes, core_hours, core_minutes, "
    "awake_hours, awake_minutes, sleep_quality, character_impact, "
    "is_processed, processed_at, created_at, updated_at"
)

_SESSION_DETAIL_SELECT = (
    _SESSION_SELECT
    + ", sleep_notes(id, user_id, sleep_session_id, content, created_at, updated_at)"
)

_SORTABLE_COLUMNS = frozenset(
    {"external_date", "total_sleep_hours", "deep_hours", "rem_hours"}
)

# Base (health, energy) per sleep quality label
_QUALITY_BASE_IMPACT: dict[str, dict[str, int]] = {
    "poor":      {"health": -2, "energy": -2},
    "fair":      {"health":  0, "energy":  1},
    "good":      {"health":  2, "energy":  3},
    "excellent": {"health":  3, "energy":  5},
}

# ±45 min window around the user's median bedtime counts as "consistent"
_CONSISTENCY_WINDOW_MINUTES = 45


# ── Low-level helpers ─────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dt_from_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _date_from_iso(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (ValueError, TypeError):
        return None


# ── Business-logic helpers ────────────────────────────────────────────────────


def _calculate_character_impact(
    sleep_quality: str, deep_hours: float, rem_hours: float
) -> dict:
    """
    Derive { health, energy } from a night's quality and phase durations.

    Base values per quality label, then additive bonuses:
        deep_hours ≥ 2.0 → health +2  |  ≥ 1.5 → health +1
        rem_hours  ≥ 2.0 → energy +2  |  ≥ 1.5 → energy +1
    Only one deep bonus and one REM bonus apply (the larger replaces the smaller).
    """
    base   = _QUALITY_BASE_IMPACT.get(sleep_quality, {"health": 0, "energy": 0})
    health = base["health"]
    energy = base["energy"]

    if deep_hours >= 2.0:
        health += 2
    elif deep_hours >= 1.5:
        health += 1

    if rem_hours >= 2.0:
        energy += 2
    elif rem_hours >= 1.5:
        energy += 1

    return {"health": health, "energy": energy}


def _flatten_detail(row: dict) -> dict:
    """Rename the PostgREST embed key 'sleep_notes' → 'notes'."""
    row["notes"] = row.pop("sleep_notes", None) or []
    return row


def _require_session(supabase, user_id: str, session_id: str) -> None:
    resp = _execute(
        supabase.table("sleep_sessions")
        .select("id")
        .eq("id", session_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Sleep session not found.", 404)


# ── Sleep consistency helpers ─────────────────────────────────────────────────


def _sleep_start_minutes(sleep_start_iso: Any) -> float | None:
    """
    Convert a timestamptz string to minutes-from-midnight (0–1440),
    then normalise pre-noon times by adding 1440 so that e.g. 01:00 (60 min)
    is treated as 1500 rather than 60.  This keeps typical late-night/early-
    morning bedtimes on the same numeric scale and prevents midnight from
    artificially inflating the standard deviation.
    """
    dt = _dt_from_iso(sleep_start_iso)
    if dt is None:
        return None
    minutes = dt.hour * 60 + dt.minute + dt.second / 60.0
    if minutes < 720:   # before 12:00 → treat as "after midnight"
        minutes += 1440.0
    return minutes


def _sleep_consistency_stddev(sessions: list[dict]) -> float | None:
    """
    Standard deviation (population) of sleep-start times in minutes.
    Returns None when fewer than two sessions have parseable timestamps.
    """
    times: list[float] = []
    for s in sessions:
        m = _sleep_start_minutes(s.get("sleep_start"))
        if m is not None:
            times.append(m)

    if len(times) < 2:
        return None

    mean     = sum(times) / len(times)
    variance = sum((t - mean) ** 2 for t in times) / len(times)
    return round(math.sqrt(variance), 2)


def _sleep_consistency_streak(sessions: list[dict]) -> int:
    """
    Count consecutive nights (going backwards from the most-recent session)
    where the sleep-start time-of-day is within ±45 minutes of the user's
    median bedtime.  Sessions must already be sorted by external_date DESC.
    """
    times: list[float] = []
    for s in sessions:
        m = _sleep_start_minutes(s.get("sleep_start"))
        if m is not None:
            times.append(m)

    if not times:
        return 0

    # Median bedtime
    sorted_times = sorted(times)
    mid          = len(sorted_times) // 2
    median       = (
        sorted_times[mid]
        if len(sorted_times) % 2
        else (sorted_times[mid - 1] + sorted_times[mid]) / 2.0
    )

    streak = 0
    for s in sessions:
        m = _sleep_start_minutes(s.get("sleep_start"))
        if m is None:
            break
        if abs(m - median) <= _CONSISTENCY_WINDOW_MINUTES:
            streak += 1
        else:
            break

    return streak


# ── Weekly aggregate ──────────────────────────────────────────────────────────


def _weekly_sleep_summary(sessions: list[dict], weeks: int = 8) -> list[dict]:
    """
    Group sessions into Mon–Sun calendar weeks.
    Returns `weeks` entries ordered oldest → newest.
    """
    today      = _today_utc()
    week_start = today - timedelta(days=today.weekday())

    result: list[dict] = []
    for i in range(weeks - 1, -1, -1):
        wk_start = week_start - timedelta(weeks=i)
        wk_end   = wk_start + timedelta(days=6)

        wk = []
        for s in sessions:
            d = _date_from_iso(s.get("external_date"))
            if d is not None and wk_start <= d <= wk_end:
                wk.append(s)

        n = len(wk)
        if n:
            avg_total = round(sum(_safe_float(s["total_sleep_hours"]) for s in wk) / n, 3)
            avg_deep  = round(sum(_safe_float(s["deep_hours"])         for s in wk) / n, 3)
            avg_rem   = round(sum(_safe_float(s["rem_hours"])          for s in wk) / n, 3)
        else:
            avg_total = avg_deep = avg_rem = 0.0

        result.append({
            "week_start":           wk_start.isoformat(),
            "nights":               n,
            "avg_total_sleep_hrs":  avg_total,
            "avg_deep_hrs":         avg_deep,
            "avg_rem_hrs":          avg_rem,
        })

    return result


# ── Import ────────────────────────────────────────────────────────────────────


def import_sleep_sessions(user_id: str, parsed: list[ParsedSleepEntry]) -> dict:
    """
    Persist a list of parsed sleep entries, silently skipping any whose
    external_date already exists for this user.

    Duplicate detection is performed in a single batch SELECT before the
    insert loop — no per-row queries.  Each INSERT is individually wrapped
    in try/except so one bad row never aborts the remaining batch.
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

    # Batch duplicate check on (user_id, external_date)
    dates = [p.external_date for p in parsed]
    resp  = _execute(
        supabase.table("sleep_sessions")
        .select("external_date")
        .eq("user_id", user_id)
        .in_("external_date", dates)
    )
    existing_dates: set[str] = {row["external_date"] for row in resp.data}

    imported:           int        = 0
    skipped_duplicates: int        = 0
    failed:             int        = 0
    inserted_sessions:  list[dict] = []

    for p in parsed:
        if p.external_date in existing_dates:
            skipped_duplicates += 1
            continue

        try:
            impact = _calculate_character_impact(
                p.sleep_quality, p.deep_hours, p.rem_hours
            )

            payload: dict = {
                "user_id":              user_id,
                "external_date":        p.external_date,
                "source":               p.source,
                "sleep_start":          p.sleep_start.isoformat(),
                "sleep_end":            p.sleep_end.isoformat(),
                "in_bed_start":         p.in_bed_start.isoformat(),
                "in_bed_end":           p.in_bed_end.isoformat(),
                "total_sleep_hours":    p.total_sleep_hours,
                "total_sleep_minutes":  p.total_sleep_minutes,
                "rem_hours":            p.rem_hours,
                "rem_minutes":          p.rem_minutes,
                "deep_hours":           p.deep_hours,
                "deep_minutes":         p.deep_minutes,
                "core_hours":           p.core_hours,
                "core_minutes":         p.core_minutes,
                "awake_hours":          p.awake_hours,
                "awake_minutes":        p.awake_minutes,
                "sleep_quality":        p.sleep_quality,
                "character_impact":     impact,
                "is_processed":         False,
                "raw_data":             p.raw_data,
            }

            insert_resp = supabase.table("sleep_sessions").insert(payload).execute()
            inserted_sessions.append(insert_resp.data[0])
            imported += 1

        except Exception:
            failed += 1

    return {
        "total_in_file":      len(parsed),
        "imported":           imported,
        "skipped_duplicates": skipped_duplicates,
        "failed":             failed,
        "sessions":           inserted_sessions,
    }


# ── Sessions ──────────────────────────────────────────────────────────────────


def list_sessions(
    user_id: str,
    *,
    from_date:     str | None = None,
    to_date:       str | None = None,
    sleep_quality: str | None = None,
    sort_by:       str        = "external_date",
    order:         str        = "desc",
    limit:         int        = 20,
    offset:        int        = 0,
) -> tuple[list[dict], int]:
    supabase = get_supabase()

    query = (
        supabase.table("sleep_sessions")
        .select(_SESSION_SELECT, count="exact")
        .eq("user_id", user_id)
    )

    if from_date:
        query = query.gte("external_date", from_date)
    if to_date:
        query = query.lte("external_date", to_date)
    if sleep_quality:
        query = query.eq("sleep_quality", sleep_quality)

    safe_sort = sort_by if sort_by in _SORTABLE_COLUMNS else "external_date"
    query = (
        query
        .order(safe_sort, desc=(order == "desc"))
        .range(offset, offset + limit - 1)
    )

    resp  = _execute(query)
    total = resp.count if resp.count is not None else len(resp.data)
    return resp.data, total


def get_session(user_id: str, session_id: str) -> dict:
    resp = _execute(
        get_supabase()
        .table("sleep_sessions")
        .select(_SESSION_DETAIL_SELECT)
        .eq("id", session_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Sleep session not found.", 404)
    return _flatten_detail(resp.data[0])


def delete_session(user_id: str, session_id: str) -> None:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)
    # sleep_notes are removed automatically by the DB CASCADE
    _execute(
        supabase.table("sleep_sessions")
        .delete()
        .eq("id", session_id)
        .eq("user_id", user_id)
    )


# ── Goals ─────────────────────────────────────────────────────────────────────


def list_goals(user_id: str) -> list[dict]:
    return _execute(
        get_supabase()
        .table("sleep_goals")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
    ).data


def create_goal(user_id: str, body: SleepGoalCreate) -> dict:
    try:
        resp = get_supabase().table("sleep_goals").insert({
            "user_id":      user_id,
            "goal_type":    body.goal_type.value,
            "target_value": body.target_value,
        }).execute()
    except Exception as exc:
        msg = str(exc).lower()
        if "unique" in msg or "duplicate" in msg:
            raise ServiceError(
                f"A '{body.goal_type.value}' goal already exists.", 409
            )
        raise ServiceError(f"Database error: {exc}", 500)
    return resp.data[0]


def update_goal(user_id: str, goal_id: str, body: SleepGoalUpdate) -> dict:
    exists = _execute(
        get_supabase()
        .table("sleep_goals")
        .select("id")
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Sleep goal not found.", 404)

    resp = _execute(
        get_supabase()
        .table("sleep_goals")
        .update({"target_value": body.target_value})
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )
    return resp.data[0]


def delete_goal(user_id: str, goal_id: str) -> None:
    supabase = get_supabase()
    exists = _execute(
        supabase.table("sleep_goals")
        .select("id")
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Sleep goal not found.", 404)
    _execute(
        supabase.table("sleep_goals")
        .delete()
        .eq("id", goal_id)
        .eq("user_id", user_id)
    )


# ── Notes ─────────────────────────────────────────────────────────────────────


def add_note(user_id: str, session_id: str, body: SleepNoteCreate) -> dict:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)
    try:
        resp = supabase.table("sleep_notes").insert({
            "user_id":          user_id,
            "sleep_session_id": session_id,
            "content":          body.content,
        }).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to add note: {exc}", 500)
    return resp.data[0]


def update_note(
    user_id: str, session_id: str, note_id: str, body: SleepNoteUpdate
) -> dict:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)

    resp = _execute(
        supabase.table("sleep_notes")
        .update({"content": body.content})
        .eq("id", note_id)
        .eq("sleep_session_id", session_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Note not found.", 404)
    return resp.data[0]


def delete_note(user_id: str, session_id: str, note_id: str) -> None:
    supabase = get_supabase()
    _require_session(supabase, user_id, session_id)

    exists = _execute(
        supabase.table("sleep_notes")
        .select("id")
        .eq("id", note_id)
        .eq("sleep_session_id", session_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Note not found.", 404)

    _execute(
        supabase.table("sleep_notes")
        .delete()
        .eq("id", note_id)
        .eq("sleep_session_id", session_id)
        .eq("user_id", user_id)
    )


# ── Stats ─────────────────────────────────────────────────────────────────────


def get_stats(user_id: str) -> dict:
    """
    Aggregate lifetime sleep statistics, computed in Python from a single
    full-table fetch — acceptable at personal-app scale where session counts
    are in the hundreds.
    """
    sessions = _execute(
        get_supabase()
        .table("sleep_sessions")
        .select(
            "external_date, sleep_start, total_sleep_hours, "
            "rem_hours, deep_hours, awake_hours, sleep_quality"
        )
        .eq("user_id", user_id)
        .order("external_date", desc=False)
    ).data

    if not sessions:
        return _empty_stats()

    n = len(sessions)

    avg_total = round(sum(_safe_float(s["total_sleep_hours"]) for s in sessions) / n, 3)
    avg_deep  = round(sum(_safe_float(s["deep_hours"])        for s in sessions) / n, 3)
    avg_rem   = round(sum(_safe_float(s["rem_hours"])         for s in sessions) / n, 3)
    avg_awake = round(sum(_safe_float(s["awake_hours"])       for s in sessions) / n, 3)

    best  = max(sessions, key=lambda s: _safe_float(s["total_sleep_hours"]))
    worst = min(sessions, key=lambda s: _safe_float(s["total_sleep_hours"]))

    breakdown: dict[str, int] = {"poor": 0, "fair": 0, "good": 0, "excellent": 0}
    for s in sessions:
        q = s.get("sleep_quality") or "fair"
        if q in breakdown:
            breakdown[q] += 1

    return {
        "total_nights":                  n,
        "avg_total_sleep_hours":         avg_total,
        "avg_deep_hours":                avg_deep,
        "avg_rem_hours":                 avg_rem,
        "avg_awake_hours":               avg_awake,
        "best_night": {
            "external_date":     best["external_date"],
            "total_sleep_hours": _safe_float(best["total_sleep_hours"]),
            "sleep_quality":     best["sleep_quality"],
        },
        "worst_night": {
            "external_date":     worst["external_date"],
            "total_sleep_hours": _safe_float(worst["total_sleep_hours"]),
            "sleep_quality":     worst["sleep_quality"],
        },
        "quality_breakdown":             breakdown,
        "weekly_summary":                _weekly_sleep_summary(sessions),
        "avg_sleep_consistency_minutes": _sleep_consistency_stddev(sessions),
    }


def _empty_stats() -> dict:
    return {
        "total_nights":                  0,
        "avg_total_sleep_hours":         None,
        "avg_deep_hours":                None,
        "avg_rem_hours":                 None,
        "avg_awake_hours":               None,
        "best_night":                    None,
        "worst_night":                   None,
        "quality_breakdown":             {"poor": 0, "fair": 0, "good": 0, "excellent": 0},
        "weekly_summary":                [],
        "avg_sleep_consistency_minutes": None,
    }


# ── Goals progress ────────────────────────────────────────────────────────────


def get_goals_progress(user_id: str) -> list[dict]:
    """
    For each goal:
      • hour-based goals (total / deep / rem): average over the last 7 days.
      • sleep_consistency: consecutive-night streak where sleep_start is
        within ±45 min of the user's median bedtime (target = desired streak
        length, e.g. target_value=7 means 7 consecutive consistent nights).

    One SELECT for goals + two narrow SELECTs for sessions — no per-goal queries.
    """
    supabase  = get_supabase()
    today     = _today_utc()

    goals = _execute(
        supabase.table("sleep_goals")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=False)
    ).data

    if not goals:
        return []

    # Recent sessions (last 7 days) for hour-based averages
    seven_days_ago = (today - timedelta(days=7)).isoformat()
    recent = _execute(
        supabase.table("sleep_sessions")
        .select("external_date, total_sleep_hours, deep_hours, rem_hours")
        .eq("user_id", user_id)
        .gte("external_date", seven_days_ago)
    ).data

    # All sessions (desc) for streak calculation
    all_sessions = _execute(
        supabase.table("sleep_sessions")
        .select("external_date, sleep_start")
        .eq("user_id", user_id)
        .order("external_date", desc=True)
    ).data

    results: list[dict] = []
    for goal in goals:
        goal_type = goal["goal_type"]
        target    = float(goal["target_value"])

        if goal_type == "total_sleep_hours":
            vals    = [_safe_float(s["total_sleep_hours"]) for s in recent]
            current = round(sum(vals) / len(vals), 3) if vals else 0.0
        elif goal_type == "deep_sleep_hours":
            vals    = [_safe_float(s["deep_hours"]) for s in recent]
            current = round(sum(vals) / len(vals), 3) if vals else 0.0
        elif goal_type == "rem_sleep_hours":
            vals    = [_safe_float(s["rem_hours"]) for s in recent]
            current = round(sum(vals) / len(vals), 3) if vals else 0.0
        else:   # sleep_consistency — streak-based
            current = float(_sleep_consistency_streak(all_sessions))

        progress = (
            min(100.0, round(current / target * 100, 1)) if target > 0 else 0.0
        )

        results.append({
            "goal":             goal,
            "current_value":    current,
            "target_value":     target,
            "progress_percent": progress,
            "is_met":           current >= target,
        })

    return results
