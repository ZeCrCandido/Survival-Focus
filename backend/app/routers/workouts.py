import json
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.dependencies.auth import CurrentUser
from app.parsers.apple_health import parse_workout
from app.schemas.workouts import (
    WorkoutGoalCreate,
    WorkoutGoalProgress,
    WorkoutGoalResponse,
    WorkoutGoalUpdate,
    WorkoutImportSummary,
    WorkoutNoteCreate,
    WorkoutNoteResponse,
    WorkoutNoteUpdate,
    WorkoutSessionDetailResponse,
    WorkoutSessionResponse,
    WorkoutStatsResponse,
)
from app.services import workouts as svc
from app.services.workouts import ServiceError

router = APIRouter(prefix="/workouts", tags=["workouts"])


# ── Helper ────────────────────────────────────────────────────────────────────


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── ROUTE ORDERING NOTE ───────────────────────────────────────────────────────
# Static path segments (/import, /stats, /goals, /goals/progress) are declared
# before parameterised routes (/{session_id}, /goals/{goal_id}).
# UUID-typed path params auto-discriminate against literal strings, but
# explicit ordering makes the intent unambiguous and matches project convention.
# ─────────────────────────────────────────────────────────────────────────────


# ── Import ────────────────────────────────────────────────────────────────────


@router.post(
    "/import",
    response_model=WorkoutImportSummary,
    status_code=status.HTTP_200_OK,
    summary="Upload an Apple Health JSON export and import all workouts inside it",
)
async def import_workouts(
    user: CurrentUser,
    file: UploadFile = File(..., description="Apple Health export .json file"),
):
    # Loose content-type check — browsers may send application/octet-stream
    # for .json files, so we also check the filename extension.
    ct = file.content_type or ""
    fn = file.filename or ""
    if "json" not in ct and not fn.lower().endswith(".json"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only JSON files are accepted (.json or application/json).",
        )

    raw_bytes = await file.read()
    try:
        payload = json.loads(raw_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse JSON: {exc}",
        )

    # Validate top-level structure before touching individual workouts.
    try:
        workouts_raw: list = payload["data"]["workouts"]
        if not isinstance(workouts_raw, list):
            raise TypeError
    except (KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expected JSON structure: { \"data\": { \"workouts\": [ ... ] } }",
        )

    # Parse stage — failures here are counted but never abort the import.
    parsed = []
    parse_failures = 0
    for raw in workouts_raw:
        try:
            parsed.append(parse_workout(raw))
        except Exception:
            parse_failures += 1

    try:
        result = svc.import_workouts(user.user_id, parsed)
    except ServiceError as exc:
        _raise(exc)

    # Parse-stage failures add to the service-stage failed counter so the
    # summary reflects every workout that could not be stored.
    result["failed"]        += parse_failures
    result["total_in_file"]  = len(workouts_raw)

    return WorkoutImportSummary(
        total_in_file=      result["total_in_file"],
        imported=           result["imported"],
        skipped_duplicates= result["skipped_duplicates"],
        failed=             result["failed"],
        sessions=[WorkoutSessionResponse.model_validate(s) for s in result["sessions"]],
    )


# ── Stats (static — before /{session_id}) ────────────────────────────────────


@router.get(
    "/stats",
    response_model=WorkoutStatsResponse,
    summary="Aggregate lifetime workout statistics for the authenticated user",
)
def get_stats(user: CurrentUser):
    try:
        return WorkoutStatsResponse.model_validate(svc.get_stats(user.user_id))
    except ServiceError as exc:
        _raise(exc)


# ── Goals — static sub-paths (before /goals/{goal_id}) ───────────────────────


@router.get(
    "/goals/progress",
    response_model=list[WorkoutGoalProgress],
    summary="Current-period progress toward each active workout goal",
)
def get_goals_progress(user: CurrentUser):
    try:
        return [
            WorkoutGoalProgress.model_validate(item)
            for item in svc.get_goals_progress(user.user_id)
        ]
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/goals",
    response_model=list[WorkoutGoalResponse],
    summary="List all workout goals for the authenticated user",
)
def list_goals(user: CurrentUser):
    try:
        return [
            WorkoutGoalResponse.model_validate(g) for g in svc.list_goals(user.user_id)
        ]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/goals",
    response_model=WorkoutGoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workout goal (one per goal_type + period combination)",
)
def create_goal(body: WorkoutGoalCreate, user: CurrentUser):
    try:
        return WorkoutGoalResponse.model_validate(svc.create_goal(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


# ── Session list (no path param — static base) ────────────────────────────────


@router.get(
    "",
    response_model=list[WorkoutSessionResponse],
    summary="List workout sessions with optional filters, sorting and pagination",
)
def list_workouts(
    user: CurrentUser,
    from_date:    date | None = Query(
        None, alias="from", description="Include sessions with started_at ≥ this date"
    ),
    to_date:      date | None = Query(
        None, alias="to", description="Include sessions with started_at ≤ this date"
    ),
    effort_level: Literal["light", "moderate", "hard", "max"] | None = None,
    sort_by: Literal[
        "started_at", "duration_seconds", "distance_km", "active_energy_kcal"
    ] = "started_at",
    order:   Literal["asc", "desc"] = "desc",
    limit:   int = Query(20, ge=1, le=100),
    offset:  int = Query(0, ge=0),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' date must not be later than 'to' date.",
        )

    try:
        sessions, _ = svc.list_workouts(
            user.user_id,
            from_date=    from_date.isoformat() if from_date else None,
            to_date=      to_date.isoformat()   if to_date   else None,
            effort_level= effort_level,
            sort_by=      sort_by,
            order=        order,
            limit=        limit,
            offset=       offset,
        )
    except ServiceError as exc:
        _raise(exc)

    return [WorkoutSessionResponse.model_validate(s) for s in sessions]


# ── Goals — parameterised routes ──────────────────────────────────────────────


@router.put(
    "/goals/{goal_id}",
    response_model=WorkoutGoalResponse,
    summary="Update a workout goal's target value",
)
def update_goal(goal_id: UUID, body: WorkoutGoalUpdate, user: CurrentUser):
    try:
        return WorkoutGoalResponse.model_validate(
            svc.update_goal(user.user_id, str(goal_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/goals/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workout goal",
)
def delete_goal(goal_id: UUID, user: CurrentUser):
    try:
        svc.delete_goal(user.user_id, str(goal_id))
    except ServiceError as exc:
        _raise(exc)


# ── Sessions — parameterised routes ───────────────────────────────────────────


@router.get(
    "/{session_id}",
    response_model=WorkoutSessionDetailResponse,
    summary="Get a single workout session with full detail and its notes",
)
def get_workout(session_id: UUID, user: CurrentUser):
    try:
        return WorkoutSessionDetailResponse.model_validate(
            svc.get_workout(user.user_id, str(session_id))
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a workout session and all its notes",
)
def delete_workout(session_id: UUID, user: CurrentUser):
    try:
        svc.delete_workout(user.user_id, str(session_id))
    except ServiceError as exc:
        _raise(exc)


# ── Notes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/{session_id}/notes",
    response_model=WorkoutNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a note to a workout session",
)
def add_note(session_id: UUID, body: WorkoutNoteCreate, user: CurrentUser):
    try:
        return WorkoutNoteResponse.model_validate(
            svc.add_note(user.user_id, str(session_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.put(
    "/{session_id}/notes/{note_id}",
    response_model=WorkoutNoteResponse,
    summary="Update the content of a workout note",
)
def update_note(
    session_id: UUID, note_id: UUID, body: WorkoutNoteUpdate, user: CurrentUser
):
    try:
        return WorkoutNoteResponse.model_validate(
            svc.update_note(user.user_id, str(session_id), str(note_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{session_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workout note",
)
def delete_note(session_id: UUID, note_id: UUID, user: CurrentUser):
    try:
        svc.delete_note(user.user_id, str(session_id), str(note_id))
    except ServiceError as exc:
        _raise(exc)
