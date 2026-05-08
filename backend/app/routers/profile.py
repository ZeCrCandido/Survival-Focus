from fastapi import APIRouter, HTTPException, status

from app.dependencies.auth import CurrentUser
from app.models.profile import AvatarType, Profile
from app.schemas.profile import (
    AvatarTypeResponse,
    OnboardingAnswerOption,
    OnboardingQuestionResponse,
    OnboardingStatusResponse,
    OnboardingSubmitRequest,
    OnboardingSubmitResponse,
    ProfileResponse,
    ProfileUpdateRequest,
)
from app.services import profile as svc
from app.services.profile import ServiceError

router = APIRouter(prefix="/profile", tags=["profile"])


# ── Conversion helpers (domain model → response schema) ───────────────────────


def _to_avatar_response(avatar: AvatarType) -> AvatarTypeResponse:
    return AvatarTypeResponse(
        id=avatar.id,
        name=avatar.name,
        description=avatar.description,
        image_url=avatar.image_url,
        traits=avatar.traits,
    )


def _to_profile_response(profile: Profile) -> ProfileResponse:
    return ProfileResponse(
        id=profile.id,
        username=profile.username,
        display_name=profile.display_name,
        bio=profile.bio,
        avatar_url=profile.avatar_url,
        avatar_type_id=profile.avatar_type_id,
        # `avatar_types` is PostgREST's join key — rename to `avatar_type` in the response.
        avatar_type=_to_avatar_response(profile.avatar_types) if profile.avatar_types else None,
        onboarding_completed=profile.onboarding_completed,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/me", response_model=ProfileResponse, summary="Get my profile")
def get_my_profile(user: CurrentUser):
    try:
        return _to_profile_response(svc.get_profile(user.user_id))
    except ServiceError as exc:
        _raise(exc)


@router.put("/me", response_model=ProfileResponse, summary="Update my profile")
def update_my_profile(body: ProfileUpdateRequest, user: CurrentUser):
    try:
        return _to_profile_response(svc.update_profile(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/onboarding",
    response_model=list[OnboardingQuestionResponse],
    summary="Get all onboarding questions",
)
def get_onboarding_questions(user: CurrentUser):
    try:
        questions = svc.get_onboarding_questions()
    except ServiceError as exc:
        _raise(exc)

    return [
        OnboardingQuestionResponse(
            id=q.id,
            question_order=q.question_order,
            question_text=q.question_text,
            # Strip `trait_weights` — that's server-side scoring data, not client data.
            answers=[OnboardingAnswerOption(label=a["label"]) for a in q.answers],
        )
        for q in questions
    ]


@router.post(
    "/onboarding",
    response_model=OnboardingSubmitResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit onboarding answers and receive avatar assignment",
)
def submit_onboarding(body: OnboardingSubmitRequest, user: CurrentUser):
    try:
        avatar = svc.submit_onboarding(user.user_id, body.answers)
    except ServiceError as exc:
        _raise(exc)

    return OnboardingSubmitResponse(
        message=f"Onboarding complete. You have been assigned the '{avatar.name}' archetype.",
        avatar_type=_to_avatar_response(avatar),
    )


@router.get(
    "/onboarding/status",
    response_model=OnboardingStatusResponse,
    summary="Check onboarding completion status",
)
def get_onboarding_status(user: CurrentUser):
    try:
        completed, avatar = svc.get_onboarding_status(user.user_id)
    except ServiceError as exc:
        _raise(exc)

    return OnboardingStatusResponse(
        completed=completed,
        avatar_type=_to_avatar_response(avatar) if avatar else None,
    )
