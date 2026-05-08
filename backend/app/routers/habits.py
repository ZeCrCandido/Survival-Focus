from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies.auth import CurrentUser
from app.schemas.habits import (
    HabitCreate,
    HabitLogCreate,
    HabitLogResponse,
    HabitLogStats,
    HabitResponse,
    HabitSkillCreate,
    HabitSkillResponse,
    HabitUpdate,
    HabitWithStats,
    TodayHabitResponse,
)
from app.services import habits as svc
from app.services.habits import ServiceError

router = APIRouter(prefix="/habits", tags=["habits"])


# ── Helpers ───────────────────────────────────────────────────────────────────


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── ORDERING NOTE ─────────────────────────────────────────────────────────────
# FastAPI (Starlette) matches routes in declaration order.  All static path
# segments (/logs/today) MUST be declared before their parameterised siblings
# (/{habit_id}) to prevent the literal strings from being captured as path
# parameters.  The same applies to /{habit_id}/logs/stats before /{habit_id}/logs.
# ─────────────────────────────────────────────────────────────────────────────


# ── Today's dashboard (static — before /{habit_id}) ──────────────────────────


@router.get(
    "/logs/today",
    response_model=list[TodayHabitResponse],
    summary="All active habits with today's log status and live streak",
)
def get_today_habits(user: CurrentUser):
    try:
        return [
            TodayHabitResponse.model_validate(item)
            for item in svc.get_today_habits(user.user_id)
        ]
    except ServiceError as exc:
        _raise(exc)


# ── Habits ────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[HabitResponse],
    summary="List all habits for the authenticated user",
)
def list_habits(user: CurrentUser):
    try:
        return [HabitResponse.model_validate(h) for h in svc.list_habits(user.user_id)]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "",
    response_model=HabitWithStats,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new habit (with optional skill mappings)",
)
def create_habit(body: HabitCreate, user: CurrentUser):
    try:
        return HabitWithStats.model_validate(svc.create_habit(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/{habit_id}",
    response_model=HabitWithStats,
    summary="Get a single habit with full detail (skills + current streak)",
)
def get_habit(habit_id: UUID, user: CurrentUser):
    try:
        return HabitWithStats.model_validate(svc.get_habit(user.user_id, str(habit_id)))
    except ServiceError as exc:
        _raise(exc)


@router.put(
    "/{habit_id}",
    response_model=HabitWithStats,
    summary="Update habit fields",
)
def update_habit(habit_id: UUID, body: HabitUpdate, user: CurrentUser):
    try:
        return HabitWithStats.model_validate(
            svc.update_habit(user.user_id, str(habit_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.patch(
    "/{habit_id}/archive",
    response_model=HabitResponse,
    summary="Soft-delete a habit — sets is_active=false, logs are preserved",
)
def archive_habit(habit_id: UUID, user: CurrentUser):
    try:
        return HabitResponse.model_validate(
            svc.archive_habit(user.user_id, str(habit_id))
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{habit_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a habit and all its logs",
)
def delete_habit(habit_id: UUID, user: CurrentUser):
    try:
        svc.delete_habit(user.user_id, str(habit_id))
    except ServiceError as exc:
        _raise(exc)


# ── Habit Logs ────────────────────────────────────────────────────────────────
# /stats is a sibling of the list route but must be declared first so that the
# literal "stats" segment is not matched as a log ID.


@router.get(
    "/{habit_id}/logs/stats",
    response_model=HabitLogStats,
    summary="Aggregated stats — streaks, completion rate, 8-week breakdown",
)
def get_log_stats(habit_id: UUID, user: CurrentUser):
    try:
        return HabitLogStats.model_validate(
            svc.get_log_stats(user.user_id, str(habit_id))
        )
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/{habit_id}/logs",
    response_model=list[HabitLogResponse],
    summary="Paginated log history for a habit (newest first)",
)
def list_logs(
    habit_id: UUID,
    user: CurrentUser,
    limit:  int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        return [
            HabitLogResponse.model_validate(lg)
            for lg in svc.list_logs(user.user_id, str(habit_id), limit, offset)
        ]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/{habit_id}/logs",
    response_model=HabitLogResponse,
    # 200 because this endpoint upserts — the caller cannot distinguish create vs update
    status_code=status.HTTP_200_OK,
    summary="Create or update today's log entry for a habit",
)
def create_or_update_log(habit_id: UUID, body: HabitLogCreate, user: CurrentUser):
    try:
        return HabitLogResponse.model_validate(
            svc.create_or_update_log(user.user_id, str(habit_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


# ── Habit Skills ──────────────────────────────────────────────────────────────


@router.get(
    "/{habit_id}/skills",
    response_model=list[HabitSkillResponse],
    summary="List skill mappings for a habit",
)
def list_skills(habit_id: UUID, user: CurrentUser):
    try:
        return [
            HabitSkillResponse.model_validate(s)
            for s in svc.list_skills(user.user_id, str(habit_id))
        ]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/{habit_id}/skills",
    response_model=HabitSkillResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a skill mapping to a healthy habit",
)
def add_skill(habit_id: UUID, body: HabitSkillCreate, user: CurrentUser):
    try:
        return HabitSkillResponse.model_validate(
            svc.add_skill(user.user_id, str(habit_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{habit_id}/skills/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a skill mapping from a habit",
)
def remove_skill(habit_id: UUID, skill_id: UUID, user: CurrentUser):
    try:
        svc.remove_skill(user.user_id, str(habit_id), str(skill_id))
    except ServiceError as exc:
        _raise(exc)
