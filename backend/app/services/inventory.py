from datetime import datetime, timezone
from uuid import UUID

from app.core.supabase_client import get_supabase
from app.schemas.character import CharacterStatsResponse
from app.schemas.inventory import (
    CatalogueItemResponse,
    EquipmentBonusesResponse,
    EquipmentResponse,
    EquipmentSlotEntry,
    EquippedItemBonusEntry,
    InventoryItemEntry,
    InventoryResponse,
    ItemUseResponse,
    ResourcesResponse,
    SkillBonusEntry,
)


# ── Errors ─────────────────────────────────────────────────────────────────────


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Constants ──────────────────────────────────────────────────────────────────

# Item types that live in the "resources" bucket of the inventory.
# The DB stores "material" (singular); the API response uses "materials".
_RESOURCE_TYPES: set[str] = {"water", "food", "material"}

# Maps DB item_type → ResourcesResponse field name.
_RESOURCE_KEY: dict[str, str] = {
    "water": "water",
    "food": "food",
    "material": "materials",
}

# Item types the player can equip into a gear slot.
_EQUIPMENT_TYPES: set[str] = {"weapon", "armor", "tool", "accessory"}

# Item types the player can consume directly; maps to the timestamp they update.
_CONSUMABLE_TS: dict[str, str] = {
    "food": "last_fed_at",
    "water": "last_hydrated_at",
    "medicine": "last_healed_at",
}

# Stat caps: stat field → its max column.
_STAT_CAPS: dict[str, str] = {
    "health": "max_health",
    "energy": "max_energy",
    "hunger": "max_hunger",
    "hydration": "max_hydration",
}

# Rarity sort order: ascending severity.
_RARITY_RANK: dict[str, int] = {
    "common": 0,
    "uncommon": 1,
    "rare": 2,
    "epic": 3,
    "legendary": 4,
}

# PostgREST join expression used on every inventory + catalogue fetch.
_ITEM_JOIN = (
    "id, item_id, quantity, "
    "items(id, name, item_type, rarity, description, effect, stat_bonus, equipment_slot)"
)

_EQUIPMENT_JOIN = (
    "id, slot, item_id, "
    "items(id, name, item_type, rarity, description, effect, stat_bonus, equipment_slot)"
)


# ── Low-level DB helpers ───────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_character(user_id: str) -> dict:
    sb = get_supabase()
    res = _execute(
        sb.table("characters").select("id").eq("user_id", user_id).limit(1)
    )
    if not res.data:
        raise ServiceError("Character not found.", 404)
    return res.data[0]


def _get_stats(character_id: str) -> dict:
    sb = get_supabase()
    res = _execute(
        sb.table("character_stats")
        .select("*")
        .eq("character_id", character_id)
        .limit(1)
    )
    if not res.data:
        raise ServiceError("Character stats not found.", 404)
    return res.data[0]


def _get_skills_by_name(character_id: str) -> dict[str, dict]:
    sb = get_supabase()
    res = _execute(
        sb.table("character_skills").select("*").eq("character_id", character_id)
    )
    return {row["skill_name"]: row for row in (res.data or [])}


def _get_inv_row(character_id: str, item_id: str) -> dict | None:
    sb = get_supabase()
    res = _execute(
        sb.table("character_inventory")
        .select("id, quantity")
        .eq("character_id", character_id)
        .eq("item_id", item_id)
        .limit(1)
    )
    return res.data[0] if res.data else None


def _decrement_inventory(inv_id: str, current_qty: int) -> None:
    sb = get_supabase()
    new_qty = current_qty - 1
    if new_qty <= 0:
        _execute(sb.table("character_inventory").delete().eq("id", inv_id))
    else:
        _execute(
            sb.table("character_inventory")
            .update({"quantity": new_qty})
            .eq("id", inv_id)
        )


def _upsert_inventory(character_id: str, item_id: str, qty_delta: int) -> None:
    """Add qty_delta to an inventory row, creating it if needed."""
    sb = get_supabase()
    inv = _get_inv_row(character_id, item_id)
    if inv:
        _execute(
            sb.table("character_inventory")
            .update({"quantity": inv["quantity"] + qty_delta})
            .eq("id", inv["id"])
        )
    else:
        _execute(
            sb.table("character_inventory").insert(
                {"character_id": character_id, "item_id": item_id, "quantity": qty_delta}
            )
        )


def _get_equipped_rows(character_id: str) -> list[dict]:
    sb = get_supabase()
    res = _execute(
        sb.table("character_equipment")
        .select(_EQUIPMENT_JOIN)
        .eq("character_id", character_id)
    )
    return res.data or []


def _build_slot_entry(row: dict) -> EquipmentSlotEntry:
    item = row.get("items") or {}
    return EquipmentSlotEntry(
        slot=row["slot"],
        item_id=row["item_id"],
        item_name=item.get("name", "Unknown"),
        item_type=item.get("item_type", "unknown"),
        rarity=item.get("rarity"),
        stat_bonus=item.get("stat_bonus"),
    )


def _build_bonuses(equipped_rows: list[dict]) -> EquipmentBonusesResponse:
    max_health_bonus = 0
    max_energy_bonus = 0
    skill_bonuses: list[SkillBonusEntry] = []
    equipped_items: list[EquippedItemBonusEntry] = []

    for row in equipped_rows:
        item = row.get("items") or {}
        bonus: dict = item.get("stat_bonus") or {}
        item_name = item.get("name", "Unknown")

        max_health_bonus += bonus.get("max_health") or 0
        max_energy_bonus += bonus.get("max_energy") or 0

        skill_name = bonus.get("skill_name")
        skill_pts = bonus.get("skill_bonus") or 0
        if skill_name and skill_pts:
            skill_bonuses.append(
                SkillBonusEntry(
                    skill_name=skill_name,
                    bonus_points=skill_pts,
                    from_item=item_name,
                )
            )

        equipped_items.append(
            EquippedItemBonusEntry(
                slot=row["slot"],
                item_name=item_name,
                rarity=item.get("rarity"),
                stat_bonus=bonus or None,
            )
        )

    return EquipmentBonusesResponse(
        max_health_bonus=max_health_bonus,
        max_energy_bonus=max_energy_bonus,
        skill_bonuses=skill_bonuses,
        equipped_items=equipped_items,
    )


def _apply_bonus(
    character_id: str,
    stats: dict,
    skills_by_name: dict[str, dict],
    stat_bonus: dict,
    *,
    reverse: bool = False,
) -> None:
    """
    Apply or reverse a stat_bonus dict against character_stats and character_skills.

    On unequip (reverse=True) the current health / energy values are clamped to
    the new (lower) max so they cannot exceed it — see module docstring.
    """
    sb = get_supabase()
    sign = -1 if reverse else 1

    stat_updates: dict = {}

    mh_delta = (stat_bonus.get("max_health") or 0) * sign
    me_delta = (stat_bonus.get("max_energy") or 0) * sign

    if mh_delta:
        new_max_health = stats["max_health"] + mh_delta
        stat_updates["max_health"] = new_max_health
        if reverse:
            stat_updates["health"] = _clamp(stats["health"], 0, new_max_health)

    if me_delta:
        new_max_energy = stats["max_energy"] + me_delta
        stat_updates["max_energy"] = new_max_energy
        if reverse:
            stat_updates["energy"] = _clamp(stats["energy"], 0, new_max_energy)

    if stat_updates:
        _execute(
            sb.table("character_stats").update(stat_updates).eq("character_id", character_id)
        )

    skill_name = stat_bonus.get("skill_name")
    skill_pts_delta = (stat_bonus.get("skill_bonus") or 0) * sign
    if skill_name and skill_pts_delta:
        skill = skills_by_name.get(skill_name)
        if skill:
            new_pts = max(0, skill["current_points"] + skill_pts_delta)
            _execute(
                sb.table("character_skills")
                .update({"current_points": new_pts})
                .eq("id", skill["id"])
            )


# ── Inventory reads ────────────────────────────────────────────────────────────


def get_full_inventory(user_id: str) -> InventoryResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    inv_res = _execute(
        sb.table("character_inventory").select(_ITEM_JOIN).eq("character_id", cid)
    )
    inv_rows: list[dict] = inv_res.data or []

    resources = ResourcesResponse()
    items: list[InventoryItemEntry] = []

    for row in inv_rows:
        item: dict = row.get("items") or {}
        itype = item.get("item_type", "")

        if itype in _RESOURCE_TYPES:
            key = _RESOURCE_KEY[itype]
            setattr(resources, key, getattr(resources, key) + row["quantity"])
        else:
            items.append(
                InventoryItemEntry(
                    inventory_id=row["id"],
                    item_id=row["item_id"],
                    quantity=row["quantity"],
                    item_name=item.get("name", "Unknown"),
                    item_type=itype,
                    rarity=item.get("rarity"),
                    description=item.get("description"),
                    effect=item.get("effect"),
                    stat_bonus=item.get("stat_bonus"),
                    equipment_slot=item.get("equipment_slot"),
                )
            )

    equipped_rows = _get_equipped_rows(cid)
    equipment = [_build_slot_entry(r) for r in equipped_rows]

    return InventoryResponse(
        resources=resources,
        items=items,
        equipment=equipment,
        total_unique_items=len(inv_rows),
    )


def get_resources(user_id: str) -> ResourcesResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    res = _execute(
        sb.table("character_inventory")
        .select("quantity, items(item_type)")
        .eq("character_id", cid)
    )

    resources = ResourcesResponse()
    for row in res.data or []:
        item = row.get("items") or {}
        itype = item.get("item_type", "")
        if itype in _RESOURCE_TYPES:
            key = _RESOURCE_KEY[itype]
            setattr(resources, key, getattr(resources, key) + row["quantity"])

    return resources


def get_items(user_id: str) -> list[InventoryItemEntry]:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    res = _execute(
        sb.table("character_inventory").select(_ITEM_JOIN).eq("character_id", cid)
    )

    result: list[InventoryItemEntry] = []
    for row in res.data or []:
        item: dict = row.get("items") or {}
        itype = item.get("item_type", "")
        if itype not in _RESOURCE_TYPES:
            result.append(
                InventoryItemEntry(
                    inventory_id=row["id"],
                    item_id=row["item_id"],
                    quantity=row["quantity"],
                    item_name=item.get("name", "Unknown"),
                    item_type=itype,
                    rarity=item.get("rarity"),
                    description=item.get("description"),
                    effect=item.get("effect"),
                    stat_bonus=item.get("stat_bonus"),
                    equipment_slot=item.get("equipment_slot"),
                )
            )

    return result


# ── Item use ──────────────────────────────────────────────────────────────────


def use_item(user_id: str, item_id: str) -> ItemUseResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    # Inventory check
    inv = _get_inv_row(cid, item_id)
    if not inv or inv["quantity"] <= 0:
        raise ServiceError("Item not found in inventory or quantity is 0.", 404)

    # Item details
    item_res = _execute(
        sb.table("items")
        .select("id, name, item_type, effect, stat_bonus, equipment_slot")
        .eq("id", item_id)
        .limit(1)
    )
    if not item_res.data:
        raise ServiceError("Item not found in catalogue.", 404)
    item = item_res.data[0]
    itype: str = item.get("item_type", "")

    # Equipment items cannot be used via this endpoint
    if itype in _EQUIPMENT_TYPES:
        raise ServiceError(
            "Use the equip endpoint to use equipment items.", 400
        )

    ts_field = _CONSUMABLE_TS.get(itype)
    if ts_field is None:
        raise ServiceError(f"Item type '{itype}' is not usable.", 400)

    effect: dict = item.get("effect") or {}
    stats = _get_stats(cid)

    # Apply all declared effects, clamped to max
    stat_updates: dict = {ts_field: _now_iso()}
    effect_applied: dict = {}
    for stat_key, max_key in _STAT_CAPS.items():
        delta = effect.get(stat_key) or 0
        if delta:
            new_val = _clamp(stats[stat_key] + delta, 0, stats[max_key])
            stat_updates[stat_key] = new_val
            effect_applied[stat_key] = delta

    _execute(
        sb.table("character_stats").update(stat_updates).eq("character_id", cid)
    )

    _decrement_inventory(inv["id"], inv["quantity"])

    updated_stats = _get_stats(cid)
    return ItemUseResponse(
        item_id=item["id"],
        item_name=item["name"],
        item_type=itype,
        effect_applied=effect_applied,
        updated_stats=CharacterStatsResponse.model_validate(updated_stats),
    )


# ── Equipment reads ───────────────────────────────────────────────────────────


def get_equipment(user_id: str) -> EquipmentResponse:
    character = _get_character(user_id)
    cid = character["id"]
    rows = _get_equipped_rows(cid)
    return EquipmentResponse(
        equipped=[_build_slot_entry(r) for r in rows],
        bonuses=_build_bonuses(rows),
    )


def get_equipment_bonuses(user_id: str) -> EquipmentBonusesResponse:
    character = _get_character(user_id)
    rows = _get_equipped_rows(character["id"])
    return _build_bonuses(rows)


# ── Equipment mutations ───────────────────────────────────────────────────────


def equip_item(user_id: str, item_id: str) -> EquipmentResponse:
    """
    Equip an item from inventory.

    If the target slot is already occupied the currently equipped item is
    automatically unequipped first (its bonuses are reversed and it is
    returned to inventory) before the new item takes its place.  This
    prevents the player from being stuck in a confirm-loop for a routine
    gear swap — see module docstring for the full rationale.
    """
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    # ── Validate inventory ───────────────────────────────────────────────────
    inv = _get_inv_row(cid, item_id)
    if not inv or inv["quantity"] < 1:
        raise ServiceError("Item not found in inventory or quantity is 0.", 404)

    # ── Validate item is equippable ──────────────────────────────────────────
    item_res = _execute(
        sb.table("items")
        .select("id, name, item_type, rarity, stat_bonus, equipment_slot")
        .eq("id", item_id)
        .limit(1)
    )
    if not item_res.data:
        raise ServiceError("Item not found in catalogue.", 404)
    item = item_res.data[0]

    slot: str | None = item.get("equipment_slot")
    if not slot:
        raise ServiceError(
            "This item cannot be equipped. Use the use endpoint for consumables.", 400
        )

    stats = _get_stats(cid)
    skills_by_name = _get_skills_by_name(cid)

    # ── Auto-unequip current occupant if slot is taken ───────────────────────
    occupied_res = _execute(
        sb.table("character_equipment")
        .select(_EQUIPMENT_JOIN)
        .eq("character_id", cid)
        .eq("slot", slot)
        .limit(1)
    )
    if occupied_res.data:
        old_row = occupied_res.data[0]
        old_item_data: dict = old_row.get("items") or {}
        old_bonus: dict = old_item_data.get("stat_bonus") or {}
        old_item_id: str = old_row["item_id"]
        eq_row_id: str = old_row["id"]

        # Reverse the old item's bonuses (re-read stats for accuracy)
        stats = _get_stats(cid)
        _apply_bonus(cid, stats, skills_by_name, old_bonus, reverse=True)

        # Return old item to inventory
        _upsert_inventory(cid, old_item_id, 1)

        # Remove from equipment table
        _execute(sb.table("character_equipment").delete().eq("id", eq_row_id))

    # ── Remove new item from inventory ────────────────────────────────────────
    _decrement_inventory(inv["id"], inv["quantity"])

    # ── Insert new equipment row ──────────────────────────────────────────────
    equip_check = _execute(
        sb.table("character_equipment")
        .select("id")
        .eq("character_id", cid)
        .eq("slot", slot)
        .limit(1)
    )
    if equip_check.data:
        _execute(
            sb.table("character_equipment")
            .update({"item_id": item_id})
            .eq("id", equip_check.data[0]["id"])
        )
    else:
        _execute(
            sb.table("character_equipment").insert(
                {"character_id": cid, "slot": slot, "item_id": item_id}
            )
        )

    # ── Apply new item's bonuses ──────────────────────────────────────────────
    new_bonus: dict = item.get("stat_bonus") or {}
    if new_bonus:
        # Re-read stats after any auto-unequip mutations above
        stats = _get_stats(cid)
        skills_by_name = _get_skills_by_name(cid)
        _apply_bonus(cid, stats, skills_by_name, new_bonus, reverse=False)

    # ── Return updated state ──────────────────────────────────────────────────
    rows = _get_equipped_rows(cid)
    return EquipmentResponse(
        equipped=[_build_slot_entry(r) for r in rows],
        bonuses=_build_bonuses(rows),
    )


def unequip_item(user_id: str, slot: str) -> EquipmentResponse:
    """
    Unequip the item in a given slot.

    The item's stat_bonus is fully reversed.  If the bonus previously raised
    max_health or max_energy, current health / energy are clamped to the new
    (lower) maximums so the character cannot carry impossible stat values —
    see module docstring for the full rationale.
    """
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    # ── Find equipped item ────────────────────────────────────────────────────
    eq_res = _execute(
        sb.table("character_equipment")
        .select(_EQUIPMENT_JOIN)
        .eq("character_id", cid)
        .eq("slot", slot)
        .limit(1)
    )
    if not eq_res.data:
        raise ServiceError(f"No item equipped in slot '{slot}'.", 404)

    eq_row = eq_res.data[0]
    item_data: dict = eq_row.get("items") or {}
    stat_bonus: dict = item_data.get("stat_bonus") or {}
    item_id: str = eq_row["item_id"]
    eq_id: str = eq_row["id"]

    # ── Reverse bonuses (with clamp on vital stats) ───────────────────────────
    stats = _get_stats(cid)
    skills_by_name = _get_skills_by_name(cid)
    _apply_bonus(cid, stats, skills_by_name, stat_bonus, reverse=True)

    # ── Return item to inventory ──────────────────────────────────────────────
    _upsert_inventory(cid, item_id, 1)

    # ── Remove equipment row ──────────────────────────────────────────────────
    _execute(sb.table("character_equipment").delete().eq("id", eq_id))

    # ── Return updated state ──────────────────────────────────────────────────
    rows = _get_equipped_rows(cid)
    return EquipmentResponse(
        equipped=[_build_slot_entry(r) for r in rows],
        bonuses=_build_bonuses(rows),
    )


# ── Catalogue ─────────────────────────────────────────────────────────────────


def get_catalogue(
    item_type: str | None = None,
    rarity: str | None = None,
    sort_by: str = "name",
) -> list[CatalogueItemResponse]:
    sb = get_supabase()

    query = sb.table("items").select(
        "id, name, item_type, rarity, description, effect, stat_bonus, equipment_slot, created_at"
    )

    if item_type:
        query = query.eq("item_type", item_type)
    if rarity:
        query = query.eq("rarity", rarity)

    # Name sort is safe to delegate to PostgREST (alphabetical is correct).
    if sort_by == "name":
        query = query.order("name")

    res = _execute(query)
    items: list[dict] = res.data or []

    # Rarity sort requires semantic ordering, not alphabetical — done in Python.
    if sort_by == "rarity":
        items.sort(key=lambda r: _RARITY_RANK.get(r.get("rarity") or "", 0))

    return [CatalogueItemResponse.model_validate(r) for r in items]


def get_catalogue_item(item_id: str) -> CatalogueItemResponse:
    sb = get_supabase()
    res = _execute(
        sb.table("items")
        .select(
            "id, name, item_type, rarity, description, effect, stat_bonus, equipment_slot, created_at"
        )
        .eq("id", item_id)
        .limit(1)
    )
    if not res.data:
        raise ServiceError("Item not found.", 404)
    return CatalogueItemResponse.model_validate(res.data[0])
