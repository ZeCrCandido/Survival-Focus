from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.dependencies.auth import CurrentUser
from app.schemas.exploration import (
    AdventureEstimateResponse,
    ExplorationAreaResponse,
    ExplorationCompleteResponse,
    ExplorationResponse,
    ExplorationStartRequest,
    ExplorationStatsResponse,
    DiscoveryResponse,
    SkillDetailResponse,
)
from app.services import exploration as svc
from app.services.exploration import ServiceError

router = APIRouter(prefix="/exploration", tags=["exploration"])


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Skills ────────────────────────────────────────────────────────────────────
#
# Declared before /{id} so static segments are never mistaken for UUIDs.
# FastAPI resolves /{id:uuid} independently, but explicit ordering is clearer.


@router.get(
    "/skills",
    response_model=list[SkillDetailResponse],
    summary="All skills with progression, contributing habits, and unlock tiers",
)
def get_skills(user: CurrentUser):
    try:
        return svc.get_skills(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/skills/{skill_name}",
    response_model=SkillDetailResponse,
    summary="Single skill with full history, contributing habits, and unlock breakdown",
)
def get_skill(skill_name: str, user: CurrentUser):
    try:
        return svc.get_skill(user.user_id, skill_name)
    except ServiceError as exc:
        _raise(exc)


# ── Static exploration data ───────────────────────────────────────────────────


@router.get(
    "/areas",
    response_model=list[ExplorationAreaResponse],
    summary="All exploration areas — is_unlocked reflects the authenticated character's progress",
)
def get_areas(user: CurrentUser):
    try:
        return svc.get_areas(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/discoveries",
    response_model=list[DiscoveryResponse],
    summary="All discoveries made by the character across every exploration",
)
def get_discoveries(user: CurrentUser):
    try:
        return svc.get_discoveries(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/stats",
    response_model=ExplorationStatsResponse,
    summary="Aggregate exploration statistics: totals, success rate, favourite area, best run",
)
def get_stats(user: CurrentUser):
    try:
        return svc.get_stats(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/adventure-estimate",
    response_model=AdventureEstimateResponse,
    summary="Estimated success chance per area based on current task impact score",
)
def get_adventure_estimate(user: CurrentUser):
    try:
        return svc.get_adventure_estimate(user.user_id)
    except ServiceError as exc:
        _raise(exc)


# ── Exploration list & detail ─────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[ExplorationResponse],
    summary="List all exploration runs for the character (newest first)",
)
def list_explorations(user: CurrentUser):
    try:
        return svc.list_explorations(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/{exploration_id}",
    response_model=ExplorationResponse,
    summary="Single exploration with its discoveries",
)
def get_exploration(exploration_id: UUID, user: CurrentUser):
    try:
        return svc.get_exploration(user.user_id, str(exploration_id))
    except ServiceError as exc:
        _raise(exc)


# ── Exploration mutations ─────────────────────────────────────────────────────


@router.post(
    "/start",
    response_model=ExplorationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new exploration run — deducts 10 energy on success",
)
def start_exploration(body: ExplorationStartRequest, user: CurrentUser):
    try:
        return svc.start_exploration(user.user_id, body.area_name)
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/{exploration_id}/complete",
    response_model=ExplorationCompleteResponse,
    summary="Complete an in-progress exploration — rolls outcome, generates loot and discoveries, queues pending reward",
)
def complete_exploration(exploration_id: UUID, user: CurrentUser):
    try:
        return svc.complete_exploration(user.user_id, str(exploration_id))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/{exploration_id}/fail",
    response_model=ExplorationResponse,
    summary="Manually fail an in-progress exploration — no loot, no consolation XP",
)
def fail_exploration(exploration_id: UUID, user: CurrentUser):
    try:
        return svc.fail_exploration(user.user_id, str(exploration_id))
    except ServiceError as exc:
        _raise(exc)
