from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.character import CharacterStatsResponse


# ── Shared item representation ─────────────────────────────────────────────────


class CatalogueItemResponse(BaseModel):
    id: UUID
    name: str
    item_type: str
    rarity: str | None = None
    description: str | None = None
    effect: dict | None = None
    stat_bonus: dict | None = None
    equipment_slot: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Inventory ─────────────────────────────────────────────────────────────────


class ResourcesResponse(BaseModel):
    water: int = 0
    food: int = 0
    materials: int = 0


class InventoryItemEntry(BaseModel):
    """One non-resource row in character_inventory, joined with items catalogue."""

    inventory_id: UUID
    item_id: UUID
    quantity: int
    item_name: str
    item_type: str
    rarity: str | None = None
    description: str | None = None
    effect: dict | None = None
    stat_bonus: dict | None = None
    equipment_slot: str | None = None


class EquipmentSlotEntry(BaseModel):
    """One row in character_equipment, joined with items catalogue."""

    slot: str
    item_id: UUID
    item_name: str
    item_type: str
    rarity: str | None = None
    stat_bonus: dict | None = None


class InventoryResponse(BaseModel):
    resources: ResourcesResponse
    items: list[InventoryItemEntry]
    equipment: list[EquipmentSlotEntry]
    total_unique_items: int


# ── Item use ──────────────────────────────────────────────────────────────────


class ItemUseResponse(BaseModel):
    item_id: UUID
    item_name: str
    item_type: str
    effect_applied: dict
    updated_stats: CharacterStatsResponse


# ── Equipment operations ──────────────────────────────────────────────────────

EquipmentSlot = Literal["weapon", "armor", "tool", "accessory"]


class EquipRequest(BaseModel):
    item_id: UUID


class UnequipRequest(BaseModel):
    slot: EquipmentSlot


# ── Bonuses ───────────────────────────────────────────────────────────────────


class SkillBonusEntry(BaseModel):
    skill_name: str
    bonus_points: int
    from_item: str


class EquippedItemBonusEntry(BaseModel):
    slot: str
    item_name: str
    rarity: str | None = None
    stat_bonus: dict | None = None


class EquipmentBonusesResponse(BaseModel):
    max_health_bonus: int = 0
    max_energy_bonus: int = 0
    skill_bonuses: list[SkillBonusEntry] = Field(default_factory=list)
    equipped_items: list[EquippedItemBonusEntry] = Field(default_factory=list)


class EquipmentResponse(BaseModel):
    equipped: list[EquipmentSlotEntry]
    bonuses: EquipmentBonusesResponse
