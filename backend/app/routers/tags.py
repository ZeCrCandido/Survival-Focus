from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.dependencies.auth import CurrentUser
from app.schemas.tags import TagCreateRequest, TagResponse, TagUpdateRequest
from app.services import tags as svc
from app.services.tags import ServiceError

router = APIRouter(prefix="/tags", tags=["tags"])


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


def _to_response(row: dict) -> TagResponse:
    return TagResponse.model_validate(row)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[TagResponse],
    summary="List my tags",
)
def list_tags(user: CurrentUser):
    try:
        return [_to_response(t) for t in svc.list_tags(user.user_id)]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "",
    response_model=TagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tag",
)
def create_tag(body: TagCreateRequest, user: CurrentUser):
    try:
        return _to_response(svc.create_tag(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


@router.put(
    "/{tag_id}",
    response_model=TagResponse,
    summary="Update a tag",
)
def update_tag(tag_id: UUID, body: TagUpdateRequest, user: CurrentUser):
    try:
        return _to_response(svc.update_tag(user.user_id, str(tag_id), body))
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tag (cascades to task_tags automatically)",
)
def delete_tag(tag_id: UUID, user: CurrentUser):
    try:
        svc.delete_tag(user.user_id, str(tag_id))
    except ServiceError as exc:
        _raise(exc)
