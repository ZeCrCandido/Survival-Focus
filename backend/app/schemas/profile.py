from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

# ── Request schemas ───────────────────────────────────────────────────────────


class ProfileUpdateRequest(BaseModel):
    username: str | None = Field(None, min_length=3, max_length=30)
    display_name: str | None = Field(None, max_length=100)
    bio: str | None = Field(None, max_length=500)
    avatar_url: str | None = None


class OnboardingAnswerSubmit(BaseModel):
    question_id: UUID
    # 0-based index into the question's `answers` array
    answer_index: int = Field(..., ge=0)


class OnboardingSubmitRequest(BaseModel):
    answers: list[OnboardingAnswerSubmit] = Field(..., min_length=1)


# ── Response schemas ──────────────────────────────────────────────────────────


class AvatarTypeResponse(BaseModel):
    id: UUID
    name: str
    description: str
    image_url: str | None
    traits: list[str]


class ProfileResponse(BaseModel):
    id: UUID
    username: str | None
    display_name: str | None
    bio: str | None
    avatar_url: str | None
    avatar_type_id: UUID | None
    # Resolved avatar type (None until onboarding is complete)
    avatar_type: AvatarTypeResponse | None
    onboarding_completed: bool
    created_at: datetime
    updated_at: datetime


class OnboardingAnswerOption(BaseModel):
    label: str
    # trait_weights intentionally omitted — scoring is a server-side concern


class OnboardingQuestionResponse(BaseModel):
    id: UUID
    question_order: int
    question_text: str
    answers: list[OnboardingAnswerOption]


class OnboardingStatusResponse(BaseModel):
    completed: bool
    avatar_type: AvatarTypeResponse | None


class OnboardingSubmitResponse(BaseModel):
    message: str
    avatar_type: AvatarTypeResponse
