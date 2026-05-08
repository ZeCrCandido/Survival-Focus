from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.dependencies.auth import CurrentUser
from app.schemas.focus import (
    FocusSessionEnd,
    FocusSessionResponse,
    FocusSessionStart,
    FocusStatsResponse,
)
from app.services import focus as svc
from app.services.focus import ServiceError

router = APIRouter(prefix="/focus", tags=["focus"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


def _to_response(row: dict) -> FocusSessionResponse:
    return FocusSessionResponse.model_validate(row)


# ── Routes ────────────────────────────────────────────────────────────────────
#
# Static path segments (/active, /stats, /history) are declared before
# the parameterised /{session_id} route to prevent ambiguous matching.


@router.post(
    "/start",
    response_model=FocusSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new focus session for a task",
)
def start_session(body: FocusSessionStart, user: CurrentUser):
    try:
        return _to_response(svc.start_session(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/active",
    response_model=FocusSessionResponse | None,
    summary="Get the currently active session (null if none)",
)
def get_active_session(user: CurrentUser):
    try:
        row = svc.get_active_session(user.user_id)
    except ServiceError as exc:
        _raise(exc)
    return _to_response(row) if row else None


@router.get(
    "/stats",
    response_model=FocusStatsResponse,
    summary="Aggregated focus statistics for the authenticated user",
)
def get_stats(user: CurrentUser):
    try:
        return FocusStatsResponse.model_validate(svc.get_stats(user.user_id))
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/history",
    response_model=list[FocusSessionResponse],
    summary="All past (ended) focus sessions, newest first",
)
def get_history(user: CurrentUser):
    try:
        return [_to_response(s) for s in svc.get_history(user.user_id)]
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/history/task/{task_id}",
    response_model=list[FocusSessionResponse],
    summary="All focus sessions for a specific task",
)
def get_task_history(task_id: UUID, user: CurrentUser):
    try:
        return [_to_response(s) for s in svc.get_task_history(user.user_id, str(task_id))]
    except ServiceError as exc:
        _raise(exc)


@router.patch(
    "/{session_id}/end",
    response_model=FocusSessionResponse,
    summary="End an active focus session (completed or abandoned)",
)
def end_session(session_id: UUID, body: FocusSessionEnd, user: CurrentUser):
    try:
        return _to_response(svc.end_session(user.user_id, str(session_id), body))
    except ServiceError as exc:
        _raise(exc)
