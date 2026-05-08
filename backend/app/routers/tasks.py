from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies.auth import CurrentUser
from app.schemas.tasks import (
    AddTagsRequest,
    TaskCreate,
    TaskHistoryResponse,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)
from app.services import tasks as svc
from app.services.tasks import ServiceError

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


def _to_response(row: dict) -> TaskResponse:
    return TaskResponse.model_validate(row)


# ── Routes ────────────────────────────────────────────────────────────────────
#
# ORDERING MATTERS: /history and other literal path segments MUST be declared
# before /{task_id}. Even though FastAPI skips UUID-typed path params when the
# segment fails UUID parsing, explicit ordering is clearer and avoids surprises.


@router.get(
    "/history",
    response_model=TaskHistoryResponse,
    summary="Paginated history of completed and cancelled tasks",
)
def get_history(
    user: CurrentUser,
    status: Literal["completed", "cancelled"] | None = None,
    category_id: UUID | None = None,
    # `from` and `to` are Python keywords, so we use Query aliases.
    from_date: datetime | None = Query(None, alias="from"),
    to_date: datetime | None = Query(None, alias="to"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    try:
        tasks, total = svc.get_history(
            user_id=user.user_id,
            status=status,
            category_id=str(category_id) if category_id else None,
            from_date=from_date.isoformat() if from_date else None,
            to_date=to_date.isoformat() if to_date else None,
            limit=limit,
            offset=offset,
        )
    except ServiceError as exc:
        _raise(exc)

    return TaskHistoryResponse(
        tasks=[_to_response(t) for t in tasks],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "",
    response_model=list[TaskResponse],
    summary="List tasks with optional filters and sorting",
)
def list_tasks(
    user: CurrentUser,
    status: TaskStatus | None = None,
    priority: TaskPriority | None = None,
    category_id: UUID | None = None,
    tag_id: UUID | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    sort_by: Literal["due_date", "priority", "created_at"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
):
    try:
        tasks = svc.list_tasks(
            user_id=user.user_id,
            status=status.value if status else None,
            priority=priority.value if priority else None,
            category_id=str(category_id) if category_id else None,
            tag_id=str(tag_id) if tag_id else None,
            due_before=due_before.isoformat() if due_before else None,
            due_after=due_after.isoformat() if due_after else None,
            sort_by=sort_by,
            order=order,
        )
    except ServiceError as exc:
        _raise(exc)

    return [_to_response(t) for t in tasks]


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get a single task with full detail including tags",
)
def get_task(task_id: UUID, user: CurrentUser):
    try:
        return _to_response(svc.get_task(user.user_id, str(task_id)))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task (with optional tags)",
)
def create_task(body: TaskCreate, user: CurrentUser):
    try:
        return _to_response(svc.create_task(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update task fields (use PATCH endpoints for status transitions)",
)
def update_task(task_id: UUID, body: TaskUpdate, user: CurrentUser):
    try:
        return _to_response(svc.update_task(user.user_id, str(task_id), body))
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task and its tag associations",
)
def delete_task(task_id: UUID, user: CurrentUser):
    try:
        svc.delete_task(user.user_id, str(task_id))
    except ServiceError as exc:
        _raise(exc)


@router.patch(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Complete a task and calculate adventure impact",
)
def complete_task(task_id: UUID, user: CurrentUser):
    try:
        return _to_response(svc.complete_task(user.user_id, str(task_id)))
    except ServiceError as exc:
        _raise(exc)


@router.patch(
    "/{task_id}/cancel",
    response_model=TaskResponse,
    summary="Cancel a task",
)
def cancel_task(task_id: UUID, user: CurrentUser):
    try:
        return _to_response(svc.cancel_task(user.user_id, str(task_id)))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/{task_id}/tags",
    response_model=TaskResponse,
    summary="Add tags to a task (idempotent — duplicates are ignored)",
)
def add_tags(task_id: UUID, body: AddTagsRequest, user: CurrentUser):
    try:
        return _to_response(svc.add_tags(user.user_id, str(task_id), body))
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{task_id}/tags/{tag_id}",
    response_model=TaskResponse,
    summary="Remove a tag from a task",
)
def remove_tag(task_id: UUID, tag_id: UUID, user: CurrentUser):
    try:
        return _to_response(svc.remove_tag(user.user_id, str(task_id), str(tag_id)))
    except ServiceError as exc:
        _raise(exc)
