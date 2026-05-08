from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.dependencies.auth import CurrentUser
from app.schemas.inventory import (
    CatalogueItemResponse,
    EquipmentBonusesResponse,
    EquipmentResponse,
    EquipRequest,
    InventoryItemEntry,
    InventoryResponse,
    ItemUseResponse,
    ResourcesResponse,
    UnequipRequest,
)
from app.services import inventory as svc
from app.services.inventory import ServiceError

router = APIRouter(prefix="/inventory", tags=["inventory"])


def _raise(exc: ServiceError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.message)


# ── Inventory reads ────────────────────────────────────────────────────────────
#
# Static sub-paths (/resources, /items, /catalogue, /equipment) are declared
# before any path-parameter routes so FastAPI never tries to resolve them as
# a parameter value.


@router.get(
    "",
    response_model=InventoryResponse,
    summary="Full inventory: resources, items, and equipped gear in one response",
)
def get_inventory(user: CurrentUser):
    try:
        return svc.get_full_inventory(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/resources",
    response_model=ResourcesResponse,
    summary="Current resource counts (water, food, materials)",
)
def get_resources(user: CurrentUser):
    try:
        return svc.get_resources(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/items",
    response_model=list[InventoryItemEntry],
    summary="All non-resource items in inventory with full catalogue details",
)
def get_items(user: CurrentUser):
    try:
        return svc.get_items(user.user_id)
    except ServiceError as exc:
        _raise(exc)


# ── Item use ──────────────────────────────────────────────────────────────────


@router.post(
    "/items/use/{item_id}",
    response_model=ItemUseResponse,
    summary="Use a consumable item from inventory (food / water / medicine)",
)
def use_item(item_id: UUID, user: CurrentUser):
    try:
        return svc.use_item(user.user_id, str(item_id))
    except ServiceError as exc:
        _raise(exc)


# ── Catalogue ─────────────────────────────────────────────────────────────────


@router.get(
    "/catalogue",
    response_model=list[CatalogueItemResponse],
    summary="Full items master catalogue — filterable by type and rarity",
)
def get_catalogue(
    user: CurrentUser,
    item_type: str | None = Query(None, description="Filter by item type (food, water, weapon, …)"),
    rarity: str | None = Query(None, description="Filter by rarity (common, uncommon, rare, epic, legendary)"),
    sort_by: Literal["name", "rarity"] = Query("name", description="Sort field"),
):
    try:
        return svc.get_catalogue(item_type=item_type, rarity=rarity, sort_by=sort_by)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/catalogue/{item_id}",
    response_model=CatalogueItemResponse,
    summary="Get a single item definition from the catalogue",
)
def get_catalogue_item(item_id: UUID, user: CurrentUser):
    try:
        return svc.get_catalogue_item(str(item_id))
    except ServiceError as exc:
        _raise(exc)


# ── Equipment reads ───────────────────────────────────────────────────────────


@router.get(
    "/equipment",
    response_model=EquipmentResponse,
    summary="All currently equipped items and their consolidated stat bonuses",
)
def get_equipment(user: CurrentUser):
    try:
        return svc.get_equipment(user.user_id)
    except ServiceError as exc:
        _raise(exc)


@router.get(
    "/equipment/bonuses",
    response_model=EquipmentBonusesResponse,
    summary="Consolidated passive stat bonuses from all equipped items",
)
def get_equipment_bonuses(user: CurrentUser):
    try:
        return svc.get_equipment_bonuses(user.user_id)
    except ServiceError as exc:
        _raise(exc)


# ── Equipment mutations ───────────────────────────────────────────────────────


@router.post(
    "/equipment/equip",
    response_model=EquipmentResponse,
    summary="Equip an item from inventory (auto-unequips any existing item in the same slot)",
)
def equip_item(body: EquipRequest, user: CurrentUser):
    try:
        return svc.equip_item(user.user_id, str(body.item_id))
    except ServiceError as exc:
        _raise(exc)


@router.post(
    "/equipment/unequip",
    response_model=EquipmentResponse,
    summary="Unequip the item in a given slot and return it to inventory",
)
def unequip_item(body: UnequipRequest, user: CurrentUser):
    try:
        return svc.unequip_item(user.user_id, body.slot)
    except ServiceError as exc:
        _raise(exc)
