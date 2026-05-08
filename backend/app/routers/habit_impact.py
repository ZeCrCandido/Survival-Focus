from datetime import date

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies.auth import CurrentUser
from app.schemas.habit_impact import (
    ImpactHistoryItem,
    ImpactHistoryResponse,
    ImpactSummaryResponse,
    PendingImpactResponse,
    ProcessImpactRequest,
    ProcessImpactResult,
)
from app.services import habit_impact as svc
from app.services.habit_impact import ServiceError

router = APIRouter(prefix="/habit-impact", tags=["habit-impact"])


# ── Helper ────────────────────────────────────────────────────────────────────


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "/pending",
    response_model=PendingImpactResponse,
    summary="All unprocessed habit impacts waiting to be applied to the character",
)
def get_pending(user: CurrentUser):
    try:
        return PendingImpactResponse.model_validate(svc.get_pending(user.user_id))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/process",
    response_model=ProcessImpactResult,
    summary="Consolidate and mark pending impacts as processed (called by character module)",
)
def process_impacts(body: ProcessImpactRequest, user: CurrentUser):
    try:
        return ProcessImpactResult.model_validate(
            svc.process_impacts(user.user_id, body)
        )
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/history",
    response_model=ImpactHistoryResponse,
    summary="Paginated list of all previously processed habit impacts",
)
def get_history(
    user: CurrentUser,
    limit:     int        = Query(20, ge=1, le=100),
    offset:    int        = Query(0, ge=0),
    from_date: date | None = Query(None, alias="from", description="Filter by logged_at ≥ this date"),
    to_date:   date | None = Query(None, alias="to",   description="Filter by logged_at ≤ this date"),
):
    if from_date and to_date and from_date > to_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'from' date must not be later than 'to' date.",
        )

    try:
        items, total = svc.get_history(
            user_id=user.user_id,
            limit=limit,
            offset=offset,
            from_date=from_date.isoformat() if from_date else None,
            to_date=to_date.isoformat() if to_date else None,
        )
    except ServiceError as exc:
        _raise(exc)

    return ImpactHistoryResponse(
        items=[ImpactHistoryItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/summary",
    response_model=ImpactSummaryResponse,
    summary="Aggregate lifetime impact summary — totals, top habits, skill XP earned",
)
def get_summary(user: CurrentUser):
    try:
        return ImpactSummaryResponse.model_validate(svc.get_summary(user.user_id))
    except ServiceError as exc:
        _raise(exc)
