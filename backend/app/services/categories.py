from collections import Counter

from app.core.supabase_client import get_supabase
from app.schemas.categories import CategoryCreateRequest, CategoryUpdateRequest


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        _raise_db_error(exc)


def _raise_db_error(exc: Exception, *, entity: str = "record") -> None:
    """Map known PostgreSQL error codes to meaningful ServiceErrors."""
    msg = str(exc)
    if "23505" in msg:  # unique_violation
        raise ServiceError(f"A {entity} with this name already exists.", 409)
    raise ServiceError(f"Database error: {exc}", 500)


# ── Categories ────────────────────────────────────────────────────────────────


def list_categories(user_id: str) -> list[dict]:
    supabase = get_supabase()

    cats = _execute(
        supabase.table("categories")
        .select("*")
        .eq("user_id", user_id)
        .order("name")
    ).data

    if not cats:
        return []

    # Fetch all task category_ids for this user in a single query, then count
    # in Python. This avoids N+1 queries and is fast enough for a personal app.
    task_rows = _execute(
        supabase.table("tasks")
        .select("category_id")
        .eq("user_id", user_id)
        .filter("category_id", "not.is", "null")
    ).data

    counts: Counter[str] = Counter(t["category_id"] for t in task_rows)

    for cat in cats:
        cat["task_count"] = counts.get(cat["id"], 0)

    return cats


def get_category(user_id: str, category_id: str) -> dict:
    resp = _execute(
        get_supabase()
        .table("categories")
        .select("*")
        .eq("id", category_id)
        .eq("user_id", user_id)  # enforces ownership
    )
    if not resp.data:
        raise ServiceError("Category not found.", 404)
    return resp.data[0]


def create_category(user_id: str, body: CategoryCreateRequest) -> dict:
    payload = {"user_id": user_id, **body.model_dump(exclude_none=True)}
    try:
        resp = get_supabase().table("categories").insert(payload).execute()
    except Exception as exc:
        _raise_db_error(exc, entity="category")
    return resp.data[0]


def update_category(
    user_id: str, category_id: str, body: CategoryUpdateRequest
) -> dict:
    # Use model_fields_set so a client can explicitly null-out optional fields
    # (e.g. clear the icon) vs simply not mentioning the field at all.
    updates = {
        field: getattr(body, field)
        for field in body.model_fields_set
    }
    if not updates:
        raise ServiceError("No updatable fields provided.", 400)

    try:
        resp = (
            get_supabase()
            .table("categories")
            .update(updates)
            .eq("id", category_id)
            .eq("user_id", user_id)  # enforces ownership
            .execute()
        )
    except Exception as exc:
        _raise_db_error(exc, entity="category")

    if not resp.data:
        raise ServiceError("Category not found.", 404)
    return resp.data[0]


def delete_category(user_id: str, category_id: str) -> None:
    supabase = get_supabase()

    # 1. Confirm the category exists and belongs to this user.
    exists = _execute(
        supabase.table("categories")
        .select("id")
        .eq("id", category_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Category not found.", 404)

    # 2. Guard: refuse deletion if any tasks are still assigned here.
    #    Use count="exact" to get the total without fetching all task rows.
    in_use = _execute(
        supabase.table("tasks")
        .select("id", count="exact")
        .eq("category_id", category_id)
        .eq("user_id", user_id)
    )
    task_count = in_use.count if in_use.count is not None else len(in_use.data)

    if task_count > 0:
        noun = "task" if task_count == 1 else "tasks"
        raise ServiceError(
            f"Cannot delete: {task_count} {noun} "
            "still assigned to this category. "
            "Reassign or delete those tasks first.",
            409,
        )

    # 3. Safe to delete.
    _execute(
        supabase.table("categories")
        .delete()
        .eq("id", category_id)
        .eq("user_id", user_id)
    )
