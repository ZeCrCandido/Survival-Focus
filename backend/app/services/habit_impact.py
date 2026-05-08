from datetime import datetime, timezone

from app.core.supabase_client import get_supabase
from app.schemas.habit_impact import ProcessImpactRequest


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# Columns fetched whenever we need to build a response that includes habit name/nature.
# PostgREST resolves the habits(...) embed via the habit_id FK automatically.
_LOG_SELECT_WITH_HABIT = (
    "id, habit_id, logged_at, processed_at, character_impact, "
    "habits(name, nature)"
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _extract_impact(row: dict) -> tuple[int, int]:
    """Pull health_delta and energy_delta out of character_impact JSONB."""
    impact = row.get("character_impact") or {}
    return impact.get("health_delta", 0), impact.get("energy_delta", 0)


def _extract_skill_rewards(row: dict) -> dict | None:
    """
    character_impact.pending_skill_rewards holds the nested skill grants.
    Returns None when the log has no skill rewards (harmful habits, missed
    healthy habits, or healthy habits with no skill mappings).
    """
    impact = row.get("character_impact") or {}
    psr = impact.get("pending_skill_rewards")
    if not psr or not isinstance(psr, dict):
        return None
    return psr


def _flatten_log(row: dict) -> dict:
    """
    Convert a PostgREST row with an embedded habits{name, nature} object into
    a flat dict suited for response schemas.  Skill rewards are lifted out of
    character_impact so callers never have to parse the nested JSONB.
    """
    habit_embed = row.get("habits") or {}
    impact      = row.get("character_impact") or {}
    psr         = _extract_skill_rewards(row)

    return {
        "log_id":     row["id"],
        "habit_id":   row["habit_id"],
        "habit_name": habit_embed.get("name", ""),
        "nature":     habit_embed.get("nature", ""),
        "logged_at":  row["logged_at"],
        "processed_at": row.get("processed_at"),
        "character_impact": {
            "health_delta": impact.get("health_delta", 0),
            "energy_delta": impact.get("energy_delta", 0),
        },
        "skill_rewards": {
            "skills": psr.get("skills", {}),
            "source": psr.get("source", ""),
        } if psr else None,
    }


# ── Pending impacts ───────────────────────────────────────────────────────────


def get_pending(user_id: str) -> dict:
    """
    Return all habit_logs with character_impact that have not yet been
    consumed by the character module (is_processed = false).
    """
    resp = _execute(
        get_supabase()
        .table("habit_logs")
        .select(_LOG_SELECT_WITH_HABIT)
        .eq("user_id", user_id)
        .eq("is_processed", False)
        .filter("character_impact", "not.is", "null")
        .order("logged_at", desc=True)
    )

    items = [_flatten_log(row) for row in resp.data]
    return {"total_pending": len(items), "items": items}


# ── Process impacts ───────────────────────────────────────────────────────────


def process_impacts(user_id: str, body: ProcessImpactRequest) -> dict:
    """
    Mark pending logs as processed and return a consolidated result for the
    character module to apply.

    Design: this service COMPUTES the deltas and marks the rows — it does NOT
    write to a character table (which does not exist yet).  The caller (character
    module) receives the totals and applies them to the character sheet itself.
    This keeps the two modules decoupled and the contract explicit.
    """
    supabase = get_supabase()

    # Build the query — start from the user's pending logs
    query = (
        supabase.table("habit_logs")
        .select("id, character_impact")
        .eq("user_id", user_id)
        .eq("is_processed", False)
        .filter("character_impact", "not.is", "null")
    )

    # Narrow to specific log IDs when provided
    if body.log_ids:
        str_ids = [str(lid) for lid in body.log_ids]
        query = query.in_("id", str_ids)

    logs = _execute(query).data

    if not logs:
        return {
            "processed_count":    0,
            "total_health_delta": 0,
            "total_energy_delta": 0,
            "skill_rewards":      [],
            "log_ids_processed":  [],
        }

    # ── Aggregate deltas ───────────────────────────────────────────────────────
    total_health: int         = 0
    total_energy: int         = 0
    skill_totals: dict[str, int] = {}
    ids_to_update: list[str]  = []

    for log in logs:
        hd, ed = _extract_impact(log)
        total_health += hd
        total_energy += ed

        psr = _extract_skill_rewards(log)
        if psr:
            for skill_name, pts in psr.get("skills", {}).items():
                skill_totals[skill_name] = skill_totals.get(skill_name, 0) + pts

        ids_to_update.append(log["id"])

    # ── Mark rows as processed ─────────────────────────────────────────────────
    # Single bulk UPDATE — far more efficient than N individual updates.
    now_iso = datetime.now(timezone.utc).isoformat()
    _execute(
        supabase.table("habit_logs")
        .update({"is_processed": True, "processed_at": now_iso})
        .in_("id", ids_to_update)
        .eq("user_id", user_id)   # belt-and-suspenders ownership guard
    )

    skill_rewards = sorted(
        [{"skill_name": k, "total_points": v} for k, v in skill_totals.items()],
        key=lambda x: -x["total_points"],
    )

    return {
        "processed_count":    len(logs),
        "total_health_delta": total_health,
        "total_energy_delta": total_energy,
        "skill_rewards":      skill_rewards,
        "log_ids_processed":  ids_to_update,
    }


# ── History ───────────────────────────────────────────────────────────────────


def get_history(
    user_id:   str,
    limit:     int,
    offset:    int,
    from_date: str | None,
    to_date:   str | None,
) -> tuple[list[dict], int]:
    """
    Return paginated processed logs with their applied impact details.
    `from_date` / `to_date` filter on logged_at (the calendar date of the habit),
    not on processed_at, so callers can inspect a specific activity period.
    """
    supabase = get_supabase()

    # ── Count query (no pagination, no column data) ────────────────────────────
    count_query = (
        supabase.table("habit_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("is_processed", True)
    )
    if from_date:
        count_query = count_query.gte("logged_at", from_date)
    if to_date:
        count_query = count_query.lte("logged_at", to_date)

    count_resp = _execute(count_query)
    total = count_resp.count or 0

    if total == 0:
        return [], 0

    # ── Data query (paginated) ─────────────────────────────────────────────────
    data_query = (
        supabase.table("habit_logs")
        .select(_LOG_SELECT_WITH_HABIT)
        .eq("user_id", user_id)
        .eq("is_processed", True)
    )
    if from_date:
        data_query = data_query.gte("logged_at", from_date)
    if to_date:
        data_query = data_query.lte("logged_at", to_date)

    data_query = (
        data_query
        .order("processed_at", desc=True)
        .range(offset, offset + limit - 1)
    )

    rows = _execute(data_query).data
    return [_flatten_log(row) for row in rows], total


# ── Summary ───────────────────────────────────────────────────────────────────


def get_summary(user_id: str) -> dict:
    """
    Aggregate all-time processed impact statistics for the user.
    Aggregation is done in Python; at personal-productivity scale the number
    of processed logs per user is in the hundreds, not millions.
    """
    supabase = get_supabase()

    # ── All processed logs ─────────────────────────────────────────────────────
    processed_resp = _execute(
        supabase.table("habit_logs")
        .select("id, habit_id, character_impact, habits(name, nature)")
        .eq("user_id", user_id)
        .eq("is_processed", True)
    )
    processed_logs = processed_resp.data

    # ── Pending count (for the UI badge) ──────────────────────────────────────
    pending_resp = _execute(
        supabase.table("habit_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("is_processed", False)
        .filter("character_impact", "not.is", "null")
    )
    pending_count = pending_resp.count or 0

    if not processed_logs:
        return _empty_summary(pending_count)

    # ── Aggregate ──────────────────────────────────────────────────────────────
    total_health: int = 0
    total_energy: int = 0
    skill_totals: dict[str, int]       = {}
    # habit_id → {"name": str, "total": int}
    habit_health: dict[str, dict]      = {}

    for log in processed_logs:
        habit_embed = log.get("habits") or {}
        habit_id    = log["habit_id"]
        habit_name  = habit_embed.get("name", "Unknown")

        hd, ed  = _extract_impact(log)
        total_health += hd
        total_energy += ed

        if habit_id not in habit_health:
            habit_health[habit_id] = {"name": habit_name, "total": 0}
        habit_health[habit_id]["total"] += hd

        psr = _extract_skill_rewards(log)
        if psr:
            for skill_name, pts in psr.get("skills", {}).items():
                skill_totals[skill_name] = skill_totals.get(skill_name, 0) + pts

    # ── Rankings ───────────────────────────────────────────────────────────────
    all_habits = [
        {
            "habit_id":           hid,
            "habit_name":         data["name"],
            "total_health_delta": data["total"],
        }
        for hid, data in habit_health.items()
    ]

    top_positive = sorted(
        (h for h in all_habits if h["total_health_delta"] > 0),
        key=lambda h: -h["total_health_delta"],
    )[:3]

    top_negative = sorted(
        (h for h in all_habits if h["total_health_delta"] < 0),
        key=lambda h: h["total_health_delta"],   # ascending: most negative first
    )[:3]

    skill_list = sorted(
        [{"skill_name": k, "total_points": v} for k, v in skill_totals.items()],
        key=lambda x: -x["total_points"],
    )

    return {
        "total_health_delta":    total_health,
        "total_energy_delta":    total_energy,
        "top_positive_habits":   top_positive,
        "top_negative_habits":   top_negative,
        "skill_points_by_skill": skill_list,
        "total_pending_count":   pending_count,
    }


def _empty_summary(pending_count: int) -> dict:
    return {
        "total_health_delta":    0,
        "total_energy_delta":    0,
        "top_positive_habits":   [],
        "top_negative_habits":   [],
        "skill_points_by_skill": [],
        "total_pending_count":   pending_count,
    }
