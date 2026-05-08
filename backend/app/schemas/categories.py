from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import HexColor

# ── Request schemas ───────────────────────────────────────────────────────────


class CategoryCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, strip_whitespace=True)
    color: HexColor
    icon: str | None = Field(None, max_length=50)


class CategoryUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100, strip_whitespace=True)
    color: HexColor | None = None
    icon: str | None = Field(None, max_length=50)


# ── Response schemas ──────────────────────────────────────────────────────────


class CategoryResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    color: str
    icon: str | None
    created_at: datetime
    updated_at: datetime


class CategoryWithTaskCount(CategoryResponse):
    """Extends the base response with the number of tasks linked to this category."""
    task_count: int
