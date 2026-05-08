from app.core.supabase_client import get_supabase
from app.schemas.tags import TagCreateRequest, TagUpdateRequest


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
    msg = str(exc)
    if "23505" in msg:  # unique_violation
        raise ServiceError(f"A {entity} with this name already exists.", 409)
    raise ServiceError(f"Database error: {exc}", 500)


# ── Tags ──────────────────────────────────────────────────────────────────────


def list_tags(user_id: str) -> list[dict]:
    resp = _execute(
        get_supabase()
        .table("tags")
        .select("*")
        .eq("user_id", user_id)
        .order("name")
    )
    return resp.data


def get_tag(user_id: str, tag_id: str) -> dict:
    resp = _execute(
        get_supabase()
        .table("tags")
        .select("*")
        .eq("id", tag_id)
        .eq("user_id", user_id)  # enforces ownership
    )
    if not resp.data:
        raise ServiceError("Tag not found.", 404)
    return resp.data[0]


def create_tag(user_id: str, body: TagCreateRequest) -> dict:
    payload = {"user_id": user_id, **body.model_dump()}
    try:
        resp = get_supabase().table("tags").insert(payload).execute()
    except Exception as exc:
        _raise_db_error(exc, entity="tag")
    return resp.data[0]


def update_tag(user_id: str, tag_id: str, body: TagUpdateRequest) -> dict:
    updates = {
        field: getattr(body, field)
        for field in body.model_fields_set
    }
    if not updates:
        raise ServiceError("No updatable fields provided.", 400)

    try:
        resp = (
            get_supabase()
            .table("tags")
            .update(updates)
            .eq("id", tag_id)
            .eq("user_id", user_id)  # enforces ownership
            .execute()
        )
    except Exception as exc:
        _raise_db_error(exc, entity="tag")

    if not resp.data:
        raise ServiceError("Tag not found.", 404)
    return resp.data[0]


def delete_tag(user_id: str, tag_id: str) -> None:
    # Confirm ownership before deleting; cascade on task_tags is handled by the DB.
    exists = _execute(
        get_supabase()
        .table("tags")
        .select("id")
        .eq("id", tag_id)
        .eq("user_id", user_id)
    )
    if not exists.data:
        raise ServiceError("Tag not found.", 404)

    _execute(
        get_supabase()
        .table("tags")
        .delete()
        .eq("id", tag_id)
        .eq("user_id", user_id)
    )
