import json
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

from app.dependencies.auth import CurrentUser
from app.parsers.apple_health_sleep import parse_sleep_entry
from app.schemas.sleep import (
    SleepGoalCreate,
    SleepGoalProgress,
    SleepGoalResponse,
    SleepGoalUpdate,
    SleepImportSummary,
    SleepNoteCreate,
    SleepNoteResponse,
    SleepNoteUpdate,
    SleepSessionDetailResponse,
    SleepSessionResponse,
    SleepStatsResponse,
)
from app.services import sleep as svc
from app.services.sleep import ServiceError

router = APIRouter(prefix="/sleep", tags=["sleep"])


# ── Helper ────────────────────────────────────────────────────────────────────


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── ROUTE ORDERING NOTE ───────────────────────────────────────────────────────
# Static path segments (/import, /stats, /goals, /goals/progress) are declared
# before parameterised routes (/{session_id}, /goals/{goal_id}).
# UUID-typed path params will NOT match literal strings, but explicit ordering
# makes the intent unambiguous and matches the project convention.
# ─────────────────────────────────────────────────────────────────────────────


# ── Import ────────────────────────────────────────────────────────────────────


@router.post(
    "/import",
    response_model=SleepImportSummary,
    status_code=status.HTTP_200_OK,
    summary="Upload an Apple Health JSON export and import all sleep sessions inside it",
)
async def import_sleep(
    user: CurrentUser,
    file: UploadFile = File(..., description="Apple Health export .json file"),
):
    ct = file.content_type or ""
    fn = file.filename    or ""
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

    # Navigate to data.metrics → find name == "sleep_analysis" → .data array
    try:
        metrics: list = payload["data"]["metrics"]
        if not isinstance(metrics, list):
            raise TypeError
    except (KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Expected JSON structure: { "data": { "metrics": [ ... ] } }',
        )

    sleep_metric = next(
        (m for m in metrics if isinstance(m, dict) and m.get("name") == "sleep_analysis"),
        None,
    )
    if sleep_metric is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='No "sleep_analysis" metric found in data.metrics.',
        )

    raw_entries: list = sleep_metric.get("data") or []
    if not isinstance(raw_entries, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='"sleep_analysis" metric has no "data" array.',
        )

    # Parse stage — failures counted but never abort the import
    parsed      = []
    parse_fails = 0
    for raw in raw_entries:
        try:
            parsed.append(parse_sleep_entry(raw))
        except Exception:
            parse_fails += 1

    try:
        result = svc.import_sleep_sessions(user.user_id, parsed)
    except ServiceError as exc:
        _raise(exc)

    result["failed"]        += parse_fails
    result["total_in_file"]  = len(raw_entries)

    return SleepImportSummary(
        total_in_file=      result["total_in_file"],
        imported=           result["imported"],
        skipped_duplicates= result["skipped_duplicates"],
        failed=             result["failed"],
        sessions=[SleepSessionResponse.model_validate(s) for s in result["sessions"]],
    )


# ── Stats (static — before /{session_id}) ─────────────────────────────────────


@router.get(
    "/stats",
    response_model=SleepStatsResponse,
    summary="Aggregate lifetime sleep statistics for the authenticated user",
)
def get_stats(user: CurrentUser):
    try:
        return SleepStatsResponse.model_validate(svc.get_stats(user.user_id))
    except ServiceError as exc:
        _raise(exc)


# ── Goals — static sub-paths (before /goals/{goal_id}) ───────────────────────


@router.get(
    "/goals/progress",
    response_model=list[SleepGoalProgress],
    summary="Current progress toward each active sleep goal",
)
def get_goals_progress(user: CurrentUser):
    try:
        return [
            SleepGoalProgress.model_validate(item)
            for item in svc.get_goals_progress(user.user_id)
        ]
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/goals",
    response_model=list[SleepGoalResponse],
    summary="List all sleep goals for the authenticated user",
)
def list_goals(user: CurrentUser):
    try:
        return [SleepGoalResponse.model_validate(g) for g in svc.list_goals(user.user_id)]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/goals",
    response_model=SleepGoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a sleep goal (one per goal_type)",
)
def create_goal(body: SleepGoalCreate, user: CurrentUser):
    try:
        return SleepGoalResponse.model_validate(svc.create_goal(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


# ── Session list (static base path) ───────────────────────────────────────────


@router.get(
    "",
    response_model=list[SleepSessionResponse],
    summary="List sleep sessions with optional filters, sorting and pagination",
)
def list_sessions(
    user: CurrentUser,
    from_date:     date | None = Query(
        None, alias="from", description="Include sessions with external_date ≥ this date"
    ),
    to_date:       date | None = Query(
        None, alias="to",   description="Include sessions with external_date ≤ this date"
    ),
    sleep_quality: Literal["poor", "fair", "good", "excellent"] | None = None,
    sort_by: Literal[
        "external_date", "total_sleep_hours", "deep_hours", "rem_hours"
    ] = "external_date",
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
        sessions, _ = svc.list_sessions(
            user.user_id,
            from_date=     from_date.isoformat() if from_date else None,
            to_date=       to_date.isoformat()   if to_date   else None,
            sleep_quality= sleep_quality,
            sort_by=       sort_by,
            order=         order,
            limit=         limit,
            offset=        offset,
        )
    except ServiceError as exc:
        _raise(exc)

    return [SleepSessionResponse.model_validate(s) for s in sessions]


# ── Goals — parameterised routes ──────────────────────────────────────────────


@router.put(
    "/goals/{goal_id}",
    response_model=SleepGoalResponse,
    summary="Update a sleep goal's target value",
)
def update_goal(goal_id: UUID, body: SleepGoalUpdate, user: CurrentUser):
    try:
        return SleepGoalResponse.model_validate(
            svc.update_goal(user.user_id, str(goal_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/goals/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a sleep goal",
)
def delete_goal(goal_id: UUID, user: CurrentUser):
    try:
        svc.delete_goal(user.user_id, str(goal_id))
    except ServiceError as exc:
        _raise(exc)


# ── Sessions — parameterised routes ───────────────────────────────────────────


@router.get(
    "/{session_id}",
    response_model=SleepSessionDetailResponse,
    summary="Get a single sleep session with full detail and its notes",
)
def get_session(session_id: UUID, user: CurrentUser):
    try:
        return SleepSessionDetailResponse.model_validate(
            svc.get_session(user.user_id, str(session_id))
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a sleep session and all its notes",
)
def delete_session(session_id: UUID, user: CurrentUser):
    try:
        svc.delete_session(user.user_id, str(session_id))
    except ServiceError as exc:
        _raise(exc)


# ── Notes ─────────────────────────────────────────────────────────────────────


@router.post(
    "/{session_id}/notes",
    response_model=SleepNoteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a note to a sleep session",
)
def add_note(session_id: UUID, body: SleepNoteCreate, user: CurrentUser):
    try:
        return SleepNoteResponse.model_validate(
            svc.add_note(user.user_id, str(session_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.put(
    "/{session_id}/notes/{note_id}",
    response_model=SleepNoteResponse,
    summary="Update the content of a sleep note",
)
def update_note(session_id: UUID, note_id: UUID, body: SleepNoteUpdate, user: CurrentUser):
    try:
        return SleepNoteResponse.model_validate(
            svc.update_note(user.user_id, str(session_id), str(note_id), body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{session_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a sleep note",
)
def delete_note(session_id: UUID, note_id: UUID, user: CurrentUser):
    try:
        svc.delete_note(user.user_id, str(session_id), str(note_id))
    except ServiceError as exc:
        _raise(exc)
