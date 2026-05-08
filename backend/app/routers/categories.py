from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from app.dependencies.auth import CurrentUser
from app.schemas.categories import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
    CategoryWithTaskCount,
)
from app.services import categories as svc
from app.services.categories import ServiceError

router = APIRouter(prefix="/categories", tags=["categories"])


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


def _to_response(row: dict) -> CategoryResponse:
    return CategoryResponse.model_validate(row)


def _to_count_response(row: dict) -> CategoryWithTaskCount:
    return CategoryWithTaskCount.model_validate(row)


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=list[CategoryWithTaskCount],
    summary="List my categories with task counts",
)
def list_categories(user: CurrentUser):
    try:
        return [_to_count_response(c) for c in svc.list_categories(user.user_id)]
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new category",
)
def create_category(body: CategoryCreateRequest, user: CurrentUser):
    try:
        return _to_response(svc.create_category(user.user_id, body))
    except ServiceError as exc:
        _raise(exc)


@router.put(
    "/{category_id}",
    response_model=CategoryResponse,
    summary="Update a category",
)
def update_category(category_id: UUID, body: CategoryUpdateRequest, user: CurrentUser):
    try:
        return _to_response(svc.update_category(user.user_id, str(category_id), body))
    except ServiceError as exc:
        _raise(exc)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category (fails if tasks are still assigned)",
)
def delete_category(category_id: UUID, user: CurrentUser):
    try:
        svc.delete_category(user.user_id, str(category_id))
    except ServiceError as exc:
        _raise(exc)
