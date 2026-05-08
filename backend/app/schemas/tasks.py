from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ── Enums ─────────────────────────────────────────────────────────────────────


class TaskPriority(str, Enum):
    low      = "low"
    medium   = "medium"
    high     = "high"
    critical = "critical"


class TaskStatus(str, Enum):
    pending     = "pending"
    in_progress = "in_progress"
    completed   = "completed"
    cancelled   = "cancelled"


class TaskFocusType(str, Enum):
    pomodoro  = "pomodoro"
    stopwatch = "stopwatch"
    none      = "none"


# ── Embedded ──────────────────────────────────────────────────────────────────


class TaskTagResponse(BaseModel):
    id:    UUID
    name:  str
    color: str


# ── Request schemas ───────────────────────────────────────────────────────────


class TaskCreate(BaseModel):
    title:       str            = Field(..., min_length=1, max_length=255, strip_whitespace=True)
    description: str | None    = Field(None, max_length=2000)
    priority:    TaskPriority   = TaskPriority.medium
    focus_type:  TaskFocusType  = TaskFocusType.none
    category_id: UUID | None   = None
    due_date:    datetime | None = None
    # Tags to attach at creation time; validated against the user's own tags.
    tag_ids:     list[UUID]    = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title:       str | None    = Field(None, min_length=1, max_length=255, strip_whitespace=True)
    description: str | None    = None
    priority:    TaskPriority | None  = None
    # Completed/cancelled transitions are handled by dedicated PATCH endpoints
    # which also trigger side-effects (impact calculation, etc.).
    status:      Literal["pending", "in_progress"] | None = None
    focus_type:  TaskFocusType | None = None
    category_id: UUID | None   = None   # send null to clear
    due_date:    datetime | None = None  # send null to clear


class AddTagsRequest(BaseModel):
    tag_ids: list[UUID] = Field(..., min_length=1)


# ── Response schemas ──────────────────────────────────────────────────────────


class TaskResponse(BaseModel):
    id:                        UUID
    user_id:                   UUID
    category_id:               UUID | None
    title:                     str
    description:               str | None
    priority:                  TaskPriority
    status:                    TaskStatus
    focus_type:                TaskFocusType
    due_date:                  datetime | None
    completed_at:              datetime | None
    estimated_adventure_impact: int | None
    # Always populated — never return a task without its tags.
    tags:                      list[TaskTagResponse]
    created_at:                datetime
    updated_at:                datetime


class TaskHistoryResponse(BaseModel):
    tasks:  list[TaskResponse]
    total:  int
    limit:  int
    offset: int
