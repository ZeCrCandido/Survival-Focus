from app.core.supabase_client import get_supabase
from app.schemas.tasks import AddTagsRequest, TaskCreate, TaskUpdate


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Constants ──────────────────────────────────────────────────────────────────

# PostgREST join expression used on every task fetch.
# task_tags → tags gives us id/name/color without exposing user_id on the tag.
_TASK_SELECT = "*, task_tags(tags(id, name, color))"

# Adventure impact scoring table (matches the spec exactly).
_PRIORITY_SCORES: dict[str, float] = {
    "low":      1.0,
    "medium":   2.0,
    "high":     3.0,
    "critical": 5.0,
}
_FOCUS_MULTIPLIERS: dict[str, float] = {
    "none":      1.0,
    "stopwatch": 1.5,
    "pomodoro":  2.0,
}

# Used for Python-side priority sort (PostgREST sorts alphabetically).
_PRIORITY_RANK: dict[str, int] = {"low": 1, "medium": 2, "high": 3, "critical": 5}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _flatten_tags(row: dict) -> dict:
    """
    Converts the nested PostgREST join structure into a flat `tags` list.

    PostgREST returns:
      "task_tags": [{"tags": {"id": ..., "name": ..., "color": ...}}, ...]

    We want:
      "tags": [{"id": ..., "name": ..., "color": ...}, ...]
    """
    row["tags"] = [
        item["tags"]
        for item in row.pop("task_tags", [])
        if item.get("tags")  # guard against null joins on tasks with no tags
    ]
    return row


def _calculate_impact(priority: str, focus_type: str) -> int:
    """
    Returns the adventure impact score for a completed task.
    Formula: priority_score × focus_multiplier, rounded to integer.
    """
    return round(_PRIORITY_SCORES[priority] * _FOCUS_MULTIPLIERS[focus_type])


def _fetch_task(supabase, user_id: str, task_id: str) -> dict:
    """Fetch a single task with tags, enforcing ownership. Raises 404 if absent."""
    resp = _execute(
        supabase.table("tasks")
        .select(_TASK_SELECT)
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not resp.data:
        raise ServiceError("Task not found.", 404)
    return _flatten_tags(resp.data[0])


def _validate_tag_ids(supabase, user_id: str, tag_ids: list[str]) -> list[str]:
    """
    Confirms every tag_id exists and belongs to the user.
    Returns the list of valid IDs; raises 404 for any that are missing.
    """
    resp = _execute(
        supabase.table("tags")
        .select("id")
        .eq("user_id", user_id)
        .in_("id", tag_ids)
    )
    valid = {row["id"] for row in resp.data}
    missing = [tid for tid in tag_ids if tid not in valid]
    if missing:
        raise ServiceError(
            f"Tags not found or don't belong to you: {', '.join(missing)}", 404
        )
    return list(valid)


# ── List & detail ──────────────────────────────────────────────────────────────


def list_tasks(
    user_id: str,
    *,
    status: str | None = None,
    priority: str | None = None,
    category_id: str | None = None,
    tag_id: str | None = None,
    due_before: str | None = None,
    due_after: str | None = None,
    sort_by: str = "created_at",
    order: str = "desc",
) -> list[dict]:
    supabase = get_supabase()

    # Tag filter requires a pre-query: find task_ids that carry this tag.
    # Combined with the later .eq("user_id") the result stays user-scoped.
    filtered_ids: list[str] | None = None
    if tag_id:
        tt = _execute(
            supabase.table("task_tags")
            .select("task_id")
            .eq("tag_id", tag_id)
        )
        if not tt.data:
            return []
        filtered_ids = [row["task_id"] for row in tt.data]

    query = (
        supabase.table("tasks")
        .select(_TASK_SELECT)
        .eq("user_id", user_id)
    )

    if status:
        query = query.eq("status", status)
    if priority:
        query = query.eq("priority", priority)
    if category_id:
        query = query.eq("category_id", category_id)
    if filtered_ids is not None:
        query = query.in_("id", filtered_ids)
    if due_before:
        query = query.lte("due_date", due_before)
    if due_after:
        query = query.gte("due_date", due_after)

    # PostgREST sorts 'priority' alphabetically (critical < high < low < medium),
    # which is wrong. We handle priority ordering in Python after the fetch.
    if sort_by != "priority":
        query = query.order(sort_by, desc=(order == "desc"))

    rows = _execute(query).data
    tasks = [_flatten_tags(row) for row in rows]

    if sort_by == "priority":
        tasks.sort(
            key=lambda t: _PRIORITY_RANK.get(t["priority"], 0),
            reverse=(order == "desc"),
        )

    return tasks


def get_task(user_id: str, task_id: str) -> dict:
    return _fetch_task(get_supabase(), user_id, task_id)


def get_history(
    user_id: str,
    *,
    status: str | None = None,
    category_id: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    supabase = get_supabase()

    query = (
        supabase.table("tasks")
        .select(_TASK_SELECT, count="exact")
        .eq("user_id", user_id)
    )

    # Default: both terminal statuses; allow the caller to narrow to one.
    if status:
        query = query.eq("status", status)
    else:
        query = query.in_("status", ["completed", "cancelled"])

    if category_id:
        query = query.eq("category_id", category_id)
    # Date range filters on created_at — consistent across both terminal statuses
    # (cancelled tasks have null completed_at, which makes that column unusable here).
    if from_date:
        query = query.gte("created_at", from_date)
    if to_date:
        query = query.lte("created_at", to_date)

    query = query.order("updated_at", desc=True).range(offset, offset + limit - 1)

    resp = _execute(query)
    total = resp.count if resp.count is not None else len(resp.data)
    return [_flatten_tags(row) for row in resp.data], total


# ── Mutations ──────────────────────────────────────────────────────────────────


def create_task(user_id: str, body: TaskCreate) -> dict:
    supabase = get_supabase()

    str_tag_ids = [str(t) for t in body.tag_ids]
    if str_tag_ids:
        str_tag_ids = _validate_tag_ids(supabase, user_id, str_tag_ids)

    payload: dict = body.model_dump(exclude={"tag_ids"}, exclude_none=True)
    payload["user_id"] = user_id
    # Normalize enum members to their string values for supabase-py serialization.
    for field in ("priority", "focus_type"):
        if field in payload and hasattr(payload[field], "value"):
            payload[field] = payload[field].value
    if "category_id" in payload:
        payload["category_id"] = str(payload["category_id"])
    if "due_date" in payload:
        payload["due_date"] = payload["due_date"].isoformat()

    try:
        task_resp = supabase.table("tasks").insert(payload).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to create task: {exc}", 500)

    task_id: str = task_resp.data[0]["id"]

    if str_tag_ids:
        tag_rows = [{"task_id": task_id, "tag_id": tid} for tid in str_tag_ids]
        try:
            supabase.table("task_tags").insert(tag_rows).execute()
        except Exception as exc:
            raise ServiceError(f"Task created but tags could not be attached: {exc}", 500)

    return _fetch_task(supabase, user_id, task_id)


def update_task(user_id: str, task_id: str, body: TaskUpdate) -> dict:
    supabase = get_supabase()

    # model_fields_set distinguishes "field not sent" from "field explicitly set to null",
    # allowing callers to clear category_id or due_date by sending null explicitly.
    updates = {field: getattr(body, field) for field in body.model_fields_set}
    if not updates:
        raise ServiceError("No updatable fields provided.", 400)

    for field in ("priority", "focus_type", "status"):
        if field in updates and updates[field] is not None and hasattr(updates[field], "value"):
            updates[field] = updates[field].value
    if "category_id" in updates and updates["category_id"] is not None:
        updates["category_id"] = str(updates["category_id"])
    if "due_date" in updates and updates["due_date"] is not None:
        updates["due_date"] = updates["due_date"].isoformat()

    try:
        resp = (
            supabase.table("tasks")
            .update(updates)
            .eq("id", task_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)

    if not resp.data:
        raise ServiceError("Task not found.", 404)

    return _fetch_task(supabase, user_id, task_id)


def delete_task(user_id: str, task_id: str) -> None:
    supabase = get_supabase()

    exists = _execute(
        supabase.table("tasks")
        .select("id")
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Task not found.", 404)

    # task_tags rows are removed automatically by the DB CASCADE constraint.
    _execute(
        supabase.table("tasks")
        .delete()
        .eq("id", task_id)
        .eq("user_id", user_id)
    )


# ── Status transitions ─────────────────────────────────────────────────────────


def complete_task(user_id: str, task_id: str) -> dict:
    supabase = get_supabase()

    row = _execute(
        supabase.table("tasks")
        .select("status, priority, focus_type")
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not row.data:
        raise ServiceError("Task not found.", 404)

    task = row.data[0]
    if task["status"] == "completed":
        raise ServiceError("Task is already completed.", 409)
    if task["status"] == "cancelled":
        raise ServiceError("Cannot complete a cancelled task. Reopen it first.", 409)

    impact = _calculate_impact(task["priority"], task["focus_type"])

    # The DB trigger sync_task_completed_at handles setting completed_at
    # automatically when status transitions to 'completed'.
    try:
        supabase.table("tasks").update({
            "status": "completed",
            "estimated_adventure_impact": impact,
        }).eq("id", task_id).eq("user_id", user_id).execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)

    return _fetch_task(supabase, user_id, task_id)


def cancel_task(user_id: str, task_id: str) -> dict:
    supabase = get_supabase()

    row = _execute(
        supabase.table("tasks")
        .select("status")
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not row.data:
        raise ServiceError("Task not found.", 404)

    current_status = row.data[0]["status"]
    if current_status == "cancelled":
        raise ServiceError("Task is already cancelled.", 409)
    if current_status == "completed":
        raise ServiceError("Cannot cancel a completed task. Reopen it first.", 409)

    try:
        supabase.table("tasks").update(
            {"status": "cancelled"}
        ).eq("id", task_id).eq("user_id", user_id).execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)

    return _fetch_task(supabase, user_id, task_id)


# ── Tag management ─────────────────────────────────────────────────────────────


def add_tags(user_id: str, task_id: str, body: AddTagsRequest) -> dict:
    supabase = get_supabase()

    task_exists = _execute(
        supabase.table("tasks")
        .select("id")
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not task_exists.data:
        raise ServiceError("Task not found.", 404)

    str_tag_ids = _validate_tag_ids(supabase, user_id, [str(t) for t in body.tag_ids])

    rows = [{"task_id": task_id, "tag_id": tid} for tid in str_tag_ids]
    try:
        # ignore_duplicates=True makes this idempotent — safe to call multiple times.
        supabase.table("task_tags").upsert(
            rows, on_conflict="task_id,tag_id", ignore_duplicates=True
        ).execute()
    except Exception as exc:
        raise ServiceError(f"Failed to add tags: {exc}", 500)

    return _fetch_task(supabase, user_id, task_id)


def remove_tag(user_id: str, task_id: str, tag_id: str) -> dict:
    supabase = get_supabase()

    task_exists = _execute(
        supabase.table("tasks")
        .select("id")
        .eq("id", task_id)
        .eq("user_id", user_id)
    )
    if not task_exists.data:
        raise ServiceError("Task not found.", 404)

    # Deleting a non-existent association is a no-op, not an error.
    _execute(
        supabase.table("task_tags")
        .delete()
        .eq("task_id", task_id)
        .eq("tag_id", tag_id)
    )

    return _fetch_task(supabase, user_id, task_id)
