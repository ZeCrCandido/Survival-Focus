from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.dependencies.auth import CurrentUser
from app.schemas.character import (
    CharacterResponse,
    CharacterSkillResponse,
    CharacterStatsResponse,
    DecayResponse,
    FeedRequest,
    HealRequest,
    HydrateRequest,
    JourneyResponse,
    PendingRewardsResponse,
    RewardProcessingReport,
)
from app.services import character as svc
from app.services.character import ServiceError

router = APIRouter(prefix="/character", tags=["character"])


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Character state ───────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=CharacterResponse,
    summary="Get full character state (stats, skills, equipment, pending rewards count)",
)
def get_character(user: CurrentUser):
    try:
        return svc.get_full_character(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "",
    response_model=CharacterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create the character for the authenticated user (called after onboarding)",
)
def create_character(user: CurrentUser):
    try:
        return svc.create_character(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/stats",
    response_model=CharacterStatsResponse,
    summary="Get current vital stats (health, energy, hunger, hydration)",
)
def get_stats(user: CurrentUser):
    try:
        return svc.get_character_stats(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/skills",
    response_model=list[CharacterSkillResponse],
    summary="Get all skill levels and progress",
)
def get_skills(user: CurrentUser):
    try:
        return svc.get_skills(user.user_id)
    except ServiceError as exc:
        _raise(exc)


# ── Consumables ───────────────────────────────────────────────────────────────


@router.post(
    "/feed",
    response_model=CharacterStatsResponse,
    summary="Feed the character (consume a food item from inventory)",
)
def feed(body: FeedRequest, user: CurrentUser):
    try:
        return svc.feed(user.user_id, str(body.item_id))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/hydrate",
    response_model=CharacterStatsResponse,
    summary="Hydrate the character (consume a water item from inventory)",
)
def hydrate(body: HydrateRequest, user: CurrentUser):
    try:
        return svc.hydrate(user.user_id, str(body.item_id))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/heal",
    response_model=CharacterStatsResponse,
    summary="Heal the character (consume a medicine item from inventory)",
)
def heal(body: HealRequest, user: CurrentUser):
    try:
        return svc.heal(user.user_id, str(body.item_id))
    except ServiceError as exc:
        _raise(exc)


# ── Decay & death ──────────────────────────────────────────────────────────────


@router.post(
    "/decay",
    response_model=DecayResponse,
    summary="Trigger stats decay (called periodically by the frontend on app open)",
)
def decay(user: CurrentUser):
    try:
        return svc.apply_decay(user.user_id)
    except ServiceError as exc:
        _raise(exc)


# ── Rewards ───────────────────────────────────────────────────────────────────


@router.post(
    "/rewards/process",
    response_model=RewardProcessingReport,
    summary="Process all pending rewards from every module and apply them to the character",
)
def process_rewards(user: CurrentUser):
    try:
        return svc.process_rewards(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/rewards/pending",
    response_model=PendingRewardsResponse,
    summary="Get all unprocessed pending rewards grouped by source type",
)
def pending_rewards(user: CurrentUser):
    try:
        return svc.get_pending_rewards(user.user_id)
    except ServiceError as exc:
        _raise(exc)


# ── Journey ───────────────────────────────────────────────────────────────────


@router.get(
    "/journey",
    response_model=JourneyResponse,
    summary="Performance report: character evolution and activity over time",
)
def journey(user: CurrentUser):
    try:
        return svc.get_journey(user.user_id)
    except ServiceError as exc:
        _raise(exc)
