from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import HexColor

# ── Request schemas ───────────────────────────────────────────────────────────


class TagCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, strip_whitespace=True)
    color: HexColor


class TagUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50, strip_whitespace=True)
    color: HexColor | None = None


# ── Response schemas ──────────────────────────────────────────────────────────


class TagResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    color: str
    created_at: datetime
