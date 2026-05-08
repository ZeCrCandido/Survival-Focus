from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AvatarType(BaseModel):
    id: UUID
    name: str
    description: str
    image_url: str | None = None
    traits: list[str]
    created_at: datetime
    updated_at: datetime


class OnboardingQuestion(BaseModel):
    id: UUID
    question_order: int
    question_text: str
    # Raw JSONB from the DB — each element has "label" and "trait_weights".
    # Kept as dicts here; the schema layer strips trait_weights before the response.
    answers: list[dict]
    created_at: datetime
    updated_at: datetime


class Profile(BaseModel):
    id: UUID  # mirrors auth.users.id
    username: str | None = None
    display_name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    avatar_type_id: UUID | None = None
    onboarding_completed: bool
    created_at: datetime
    updated_at: datetime
    # Populated when the profile is fetched with a join on avatar_types.
    # The field name matches PostgREST's default join key (the table name).
    avatar_types: AvatarType | None = None
