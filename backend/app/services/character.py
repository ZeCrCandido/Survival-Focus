from datetime import date, datetime, timedelta, timezone

from app.core.supabase_client import get_supabase
from app.schemas.character import (
    CharacterResponse,
    CharacterSkillResponse,
    CharacterStatsResponse,
    DecayResponse,
    EquippedItemSummary,
    JourneyResponse,
    LevelUpEvent,
    PendingRewardsResponse,
    RewardProcessingReport,
    ResourcesGained,
    SourceBreakdown,
)


# ── Errors ─────────────────────────────────────────────────────────────────────


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Constants ──────────────────────────────────────────────────────────────────

SKILLS = ["strength", "endurance", "focus", "resilience", "agility", "survival"]

_DEFAULT_STATS: dict = {
    "health": 100,
    "max_health": 100,
    "energy": 100,
    "max_energy": 100,
    "hunger": 100,
    "max_hunger": 100,
    "hydration": 100,
    "max_hydration": 100,
}

# Vital stats after death revival — intentionally punishing to create tension.
_REVIVAL_STATS = {"health": 10, "hunger": 20, "hydration": 20}

# Stat fields that can be restored by item effects, mapped to their max column.
_STAT_CAPS: dict[str, str] = {
    "health": "max_health",
    "energy": "max_energy",
    "hunger": "max_hunger",
    "hydration": "max_hydration",
}

# All reward source types tracked in the processing report.
_REWARD_SOURCES = ("focus_session", "habit_log", "workout_session", "sleep_session")


# ── Utilities ──────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _clamp(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _points_to_next_level(level: int) -> int:
    """XP required to advance from `level` to `level + 1`."""
    return level * 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Low-level DB helpers ───────────────────────────────────────────────────────


def _get_character_by_user(user_id: str) -> dict:
    sb = get_supabase()
    res = _execute(
        sb.table("characters").select("*").eq("user_id", user_id).limit(1)
    )
    if not res.data:
        raise ServiceError("Character not found.", 404)
    return res.data[0]


def _get_stats(character_id: str) -> dict:
    sb = get_supabase()
    res = _execute(
        sb.table("character_stats").select("*").eq("character_id", character_id).limit(1)
    )
    if not res.data:
        raise ServiceError("Character stats not found.", 404)
    return res.data[0]


def _get_skills(character_id: str) -> list[dict]:
    sb = get_supabase()
    res = _execute(
        sb.table("character_skills").select("*").eq("character_id", character_id)
    )
    return res.data or []


def _get_equipment(character_id: str) -> list[dict]:
    sb = get_supabase()
    res = _execute(
        sb.table("character_equipment")
        .select("slot, item_id, items(name, item_type)")
        .eq("character_id", character_id)
    )
    rows = []
    for row in res.data or []:
        item_info = row.get("items") or {}
        rows.append(
            {
                "slot": row["slot"],
                "item_id": row["item_id"],
                "item_name": item_info.get("name", "Unknown"),
                "item_type": item_info.get("item_type", "unknown"),
            }
        )
    return rows


def _count_pending(character_id: str) -> int:
    sb = get_supabase()
    res = _execute(
        sb.table("pending_rewards")
        .select("id", count="exact")
        .eq("character_id", character_id)
        .eq("is_processed", False)
    )
    return res.count or 0


def _assemble_character(
    character: dict,
    stats: dict,
    skills: list[dict],
    equipment: list[dict],
    pending_count: int,
) -> CharacterResponse:
    return CharacterResponse(
        **{
            k: v
            for k, v in character.items()
            if k not in ("stats", "skills", "equipment", "pending_rewards_count")
        },
        stats=CharacterStatsResponse.model_validate(stats),
        skills=[CharacterSkillResponse.model_validate(s) for s in skills],
        equipment=[EquippedItemSummary.model_validate(e) for e in equipment],
        pending_rewards_count=pending_count,
    )


# ── Public: character state ────────────────────────────────────────────────────


def get_full_character(user_id: str) -> CharacterResponse:
    character = _get_character_by_user(user_id)
    cid = character["id"]
    return _assemble_character(
        character,
        _get_stats(cid),
        _get_skills(cid),
        _get_equipment(cid),
        _count_pending(cid),
    )


def create_character(user_id: str) -> CharacterResponse:
    sb = get_supabase()

    existing = _execute(
        sb.table("characters").select("id").eq("user_id", user_id).limit(1)
    )
    if existing.data:
        raise ServiceError("Character already exists for this user.", 409)

    profile_res = _execute(
        sb.table("profiles").select("avatar_type_id").eq("id", user_id).limit(1)
    )
    if not profile_res.data:
        raise ServiceError("User profile not found.", 404)
    avatar_type_id = profile_res.data[0].get("avatar_type_id")

    char_res = _execute(
        sb.table("characters")
        .insert(
            {
                "user_id": user_id,
                "avatar_type_id": avatar_type_id,
                "level": 1,
                "experience_points": 0,
                "is_alive": True,
                "death_count": 0,
                "days_survived": 0,
            }
        )
        .select()
    )
    character = char_res.data[0]
    cid = character["id"]

    stats_res = _execute(
        sb.table("character_stats")
        .insert({"character_id": cid, **_DEFAULT_STATS})
        .select()
    )
    stats = stats_res.data[0]

    skill_rows = [
        {
            "character_id": cid,
            "skill_name": skill,
            "current_points": 0,
            "level": 1,
            "points_to_next_level": _points_to_next_level(1),
        }
        for skill in SKILLS
    ]
    _execute(sb.table("character_skills").insert(skill_rows))
    skills = _get_skills(cid)

    return _assemble_character(character, stats, skills, [], 0)


def get_character_stats(user_id: str) -> CharacterStatsResponse:
    character = _get_character_by_user(user_id)
    return CharacterStatsResponse.model_validate(_get_stats(character["id"]))


def get_skills(user_id: str) -> list[CharacterSkillResponse]:
    character = _get_character_by_user(user_id)
    return [CharacterSkillResponse.model_validate(s) for s in _get_skills(character["id"])]


# ── Public: consumable items ───────────────────────────────────────────────────


def _consume_item(
    user_id: str,
    item_id: str,
    expected_type: str,
    timestamp_field: str,
) -> CharacterStatsResponse:
    """
    Shared logic for feed / hydrate / heal.

    Applies every stat effect declared in items.effect (clamped at max),
    decrements the inventory quantity, and stamps the relevant timestamp.
    """
    sb = get_supabase()
    character = _get_character_by_user(user_id)
    cid = character["id"]

    # Verify inventory row exists with stock
    inv_res = _execute(
        sb.table("character_inventory")
        .select("id, quantity")
        .eq("character_id", cid)
        .eq("item_id", item_id)
        .limit(1)
    )
    if not inv_res.data or inv_res.data[0]["quantity"] <= 0:
        raise ServiceError(
            "Item not found in inventory or quantity is 0.", 404
        )
    inv = inv_res.data[0]

    # Verify item exists and is the right type
    item_res = _execute(
        sb.table("items").select("id, item_type, effect").eq("id", item_id).limit(1)
    )
    if not item_res.data:
        raise ServiceError("Item not found.", 404)
    item = item_res.data[0]

    if item.get("item_type") != expected_type:
        raise ServiceError(
            f"Invalid item type: expected '{expected_type}', got '{item.get('item_type')}'.",
            400,
        )

    effect: dict = item.get("effect") or {}
    stats = _get_stats(cid)

    # Build stat updates from the item's effect dict — any declared field is applied
    updates: dict = {timestamp_field: _now_iso()}
    for stat_key, max_key in _STAT_CAPS.items():
        delta = effect.get(stat_key, 0) or 0
        if delta != 0:
            updates[stat_key] = _clamp(stats[stat_key] + delta, 0, stats[max_key])

    _execute(
        sb.table("character_stats").update(updates).eq("character_id", cid)
    )

    # Consume one unit; delete the row if stock hits zero
    new_qty = inv["quantity"] - 1
    if new_qty <= 0:
        _execute(sb.table("character_inventory").delete().eq("id", inv["id"]))
    else:
        _execute(
            sb.table("character_inventory")
            .update({"quantity": new_qty})
            .eq("id", inv["id"])
        )

    return CharacterStatsResponse.model_validate(_get_stats(cid))


def feed(user_id: str, item_id: str) -> CharacterStatsResponse:
    return _consume_item(user_id, item_id, "food", "last_fed_at")


def hydrate(user_id: str, item_id: str) -> CharacterStatsResponse:
    return _consume_item(user_id, item_id, "water", "last_hydrated_at")


def heal(user_id: str, item_id: str) -> CharacterStatsResponse:
    return _consume_item(user_id, item_id, "medicine", "last_healed_at")


# ── Public: decay & death ─────────────────────────────────────────────────────


def apply_decay(user_id: str) -> DecayResponse:
    sb = get_supabase()
    character = _get_character_by_user(user_id)
    cid = character["id"]

    _execute(sb.rpc("apply_stats_decay", {"p_character_id": cid}))

    # Re-read character state after the Postgres function mutated it
    char_res = _execute(
        sb.table("characters").select("*").eq("id", cid).limit(1)
    )
    char = char_res.data[0]
    death_event = not char.get("is_alive", True)

    if death_event:
        # Revive with penalties — see rationale in module docstring
        _execute(
            sb.table("characters")
            .update({"is_alive": True, "death_count": char["death_count"] + 1})
            .eq("id", cid)
        )
        _execute(
            sb.table("character_stats")
            .update(_REVIVAL_STATS)
            .eq("character_id", cid)
        )

    return DecayResponse(
        death_event=death_event,
        stats=CharacterStatsResponse.model_validate(_get_stats(cid)),
    )


# ── Public: reward processing ─────────────────────────────────────────────────


def _upsert_resource(character_id: str, resource_type: str, qty: int) -> None:
    """
    Add `qty` units of a resource to the character's inventory.

    Looks up the canonical base item for that resource type in the items table
    (ordered by creation date so the earliest seed item wins).  If no item of
    that type exists yet, the resource is silently skipped — nothing to upsert
    against.
    """
    if qty <= 0:
        return
    sb = get_supabase()

    item_res = _execute(
        sb.table("items")
        .select("id")
        .eq("item_type", resource_type)
        .order("created_at")
        .limit(1)
    )
    if not item_res.data:
        return  # No base item registered for this type

    item_id = item_res.data[0]["id"]

    inv_res = _execute(
        sb.table("character_inventory")
        .select("id, quantity")
        .eq("character_id", character_id)
        .eq("item_id", item_id)
        .limit(1)
    )
    if inv_res.data:
        _execute(
            sb.table("character_inventory")
            .update({"quantity": inv_res.data[0]["quantity"] + qty})
            .eq("id", inv_res.data[0]["id"])
        )
    else:
        _execute(
            sb.table("character_inventory").insert(
                {"character_id": character_id, "item_id": item_id, "quantity": qty}
            )
        )


def _apply_skill_points(skill: dict, pts_to_add: int) -> bool:
    """
    Add `pts_to_add` to a skill, level it up in a loop if threshold is met,
    and persist the final state.  Returns True if at least one level-up occurred.
    """
    if pts_to_add <= 0:
        return False

    sb = get_supabase()
    current_pts = skill["current_points"] + pts_to_add
    current_lvl = skill["level"]
    levelled_up = False

    while current_pts >= _points_to_next_level(current_lvl):
        current_pts -= _points_to_next_level(current_lvl)
        current_lvl += 1
        levelled_up = True

    _execute(
        sb.table("character_skills")
        .update(
            {
                "current_points": current_pts,
                "level": current_lvl,
                "points_to_next_level": _points_to_next_level(current_lvl),
            }
        )
        .eq("id", skill["id"])
    )
    return levelled_up


def process_rewards(user_id: str) -> RewardProcessingReport:
    sb = get_supabase()
    character = _get_character_by_user(user_id)
    cid = character["id"]
    old_level = character["level"]

    rewards_res = _execute(
        sb.table("pending_rewards")
        .select("*")
        .eq("character_id", cid)
        .eq("is_processed", False)
        .order("created_at")
    )
    rewards: list[dict] = rewards_res.data or []

    # Early return when nothing is queued — still run level-up check
    if not rewards:
        _execute(sb.rpc("calculate_level_up", {"p_character_id": cid}))
        updated_char = _get_character_by_user(user_id)
        return RewardProcessingReport(
            processed_count=0,
            total_health_delta=0,
            total_energy_delta=0,
            total_experience_gained=0,
            levelled_up=False,
            new_level=updated_char["level"],
            skills_levelled_up=[],
            resources_gained=ResourcesGained(),
            character_stats=CharacterStatsResponse.model_validate(_get_stats(cid)),
            source_breakdown=SourceBreakdown(),
        )

    # ── Accumulate across all rewards ─────────────────────────────────────────
    total_health_delta = 0
    total_energy_delta = 0
    total_xp = 0
    total_resources: dict[str, int] = {"water": 0, "food": 0, "materials": 0}
    skill_point_totals: dict[str, int] = {s: 0 for s in SKILLS}
    source_counts: dict[str, int] = {s: 0 for s in _REWARD_SOURCES}

    for reward in rewards:
        total_health_delta += reward.get("health_delta") or 0
        total_energy_delta += reward.get("energy_delta") or 0
        total_xp += reward.get("experience_points") or 0

        resources: dict = reward.get("resources") or {}
        for r_key in ("water", "food", "materials"):
            total_resources[r_key] += resources.get(r_key) or 0

        skill_rewards: dict = reward.get("skill_rewards") or {}
        for skill_name, pts in skill_rewards.items():
            if skill_name in skill_point_totals:
                skill_point_totals[skill_name] += pts or 0

        src = reward.get("source_type", "")
        if src in source_counts:
            source_counts[src] += 1

    # ── Apply stat deltas (single batch update) ────────────────────────────────
    stats = _get_stats(cid)
    new_health = _clamp(stats["health"] + total_health_delta, 0, stats["max_health"])
    new_energy = _clamp(stats["energy"] + total_energy_delta, 0, stats["max_energy"])
    _execute(
        sb.table("character_stats")
        .update({"health": new_health, "energy": new_energy})
        .eq("character_id", cid)
    )

    # ── Apply XP (uncapped — see rationale in module docstring) ───────────────
    new_xp = character["experience_points"] + total_xp
    _execute(
        sb.table("characters")
        .update({"experience_points": new_xp})
        .eq("id", cid)
    )

    # ── Upsert resources into inventory ───────────────────────────────────────
    for r_key, qty in total_resources.items():
        _upsert_resource(cid, r_key, qty)

    # ── Apply skill points and check level-ups ─────────────────────────────────
    skills_levelled_up: list[str] = []
    current_skills = {s["skill_name"]: s for s in _get_skills(cid)}
    for skill_name, pts in skill_point_totals.items():
        skill = current_skills.get(skill_name)
        if skill and pts > 0:
            if _apply_skill_points(skill, pts):
                skills_levelled_up.append(skill_name)

    # ── Mark all processed ────────────────────────────────────────────────────
    reward_ids = [r["id"] for r in rewards]
    _execute(
        sb.table("pending_rewards")
        .update({"is_processed": True, "processed_at": _now_iso()})
        .in_("id", reward_ids)
    )

    # ── Character level-up check (delegated to Postgres) ──────────────────────
    _execute(sb.rpc("calculate_level_up", {"p_character_id": cid}))

    updated_char = _get_character_by_user(user_id)
    updated_stats = _get_stats(cid)

    return RewardProcessingReport(
        processed_count=len(rewards),
        total_health_delta=total_health_delta,
        total_energy_delta=total_energy_delta,
        total_experience_gained=total_xp,
        levelled_up=updated_char["level"] > old_level,
        new_level=updated_char["level"],
        skills_levelled_up=skills_levelled_up,
        resources_gained=ResourcesGained(**total_resources),
        character_stats=CharacterStatsResponse.model_validate(updated_stats),
        source_breakdown=SourceBreakdown(**source_counts),
    )


def get_pending_rewards(user_id: str) -> PendingRewardsResponse:
    sb = get_supabase()
    character = _get_character_by_user(user_id)
    cid = character["id"]

    res = _execute(
        sb.table("pending_rewards")
        .select("*")
        .eq("character_id", cid)
        .eq("is_processed", False)
        .order("created_at")
    )
    rewards: list[dict] = res.data or []

    grouped: dict[str, list[dict]] = {}
    for reward in rewards:
        src = reward.get("source_type", "unknown")
        grouped.setdefault(src, []).append(reward)

    return PendingRewardsResponse(total_pending=len(rewards), by_source=grouped)


# ── Public: journey ───────────────────────────────────────────────────────────


def _calculate_streak(user_id: str) -> int:
    """
    Walks backwards from today counting consecutive days on which at least one
    activity occurred (task completed, habit logged, workout, or sleep record).
    All timestamps are normalised to UTC date before the set membership check.
    """
    sb = get_supabase()
    active_dates: set[date] = set()

    def _to_date(ts: str) -> date:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date()

    tasks_res = _execute(
        sb.table("tasks")
        .select("updated_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
    )
    for row in tasks_res.data or []:
        if row.get("updated_at"):
            active_dates.add(_to_date(row["updated_at"]))

    habits_res = _execute(
        sb.table("habit_logs").select("logged_at").eq("user_id", user_id)
    )
    for row in habits_res.data or []:
        if row.get("logged_at"):
            active_dates.add(_to_date(row["logged_at"]))

    workouts_res = _execute(
        sb.table("workout_sessions").select("started_at").eq("user_id", user_id)
    )
    for row in workouts_res.data or []:
        if row.get("started_at"):
            active_dates.add(_to_date(row["started_at"]))

    sleep_res = _execute(
        sb.table("sleep_sessions").select("external_date").eq("user_id", user_id)
    )
    for row in sleep_res.data or []:
        if row.get("external_date"):
            active_dates.add(date.fromisoformat(row["external_date"]))

    streak = 0
    cursor = datetime.now(timezone.utc).date()
    while cursor in active_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def get_journey(user_id: str) -> JourneyResponse:
    sb = get_supabase()
    character = _get_character_by_user(user_id)
    cid = character["id"]

    created_at = datetime.fromisoformat(character["created_at"])
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - created_at).days

    tasks_res = _execute(
        sb.table("tasks")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("status", "completed")
    )
    total_tasks = tasks_res.count or 0

    focus_res = _execute(
        sb.table("focus_sessions").select("duration_seconds").eq("user_id", user_id)
    )
    total_focus_minutes = (
        sum((r.get("duration_seconds") or 0) for r in focus_res.data or []) // 60
    )

    habits_res = _execute(
        sb.table("habit_logs")
        .select("id", count="exact")
        .eq("user_id", user_id)
    )
    total_habits = habits_res.count or 0

    workouts_res = _execute(
        sb.table("workout_sessions")
        .select("id", count="exact")
        .eq("user_id", user_id)
    )
    total_workouts = workouts_res.count or 0

    sleep_res = _execute(
        sb.table("sleep_sessions")
        .select("id", count="exact")
        .eq("user_id", user_id)
    )
    total_sleep = sleep_res.count or 0

    processed_rewards_res = _execute(
        sb.table("pending_rewards")
        .select("resources, experience_points")
        .eq("character_id", cid)
        .eq("is_processed", True)
    )
    total_water = total_food = total_materials = 0
    total_xp_earned = 0
    for row in processed_rewards_res.data or []:
        r = row.get("resources") or {}
        total_water += r.get("water") or 0
        total_food += r.get("food") or 0
        total_materials += r.get("materials") or 0
        total_xp_earned += row.get("experience_points") or 0

    levels_res = _execute(
        sb.table("level_up_events")
        .select("old_level, new_level, levelled_up_at")
        .eq("character_id", cid)
        .order("levelled_up_at")
    )
    level_progression = [
        LevelUpEvent.model_validate(row) for row in (levels_res.data or [])
    ]

    return JourneyResponse(
        character_age_days=age_days,
        total_tasks_completed=total_tasks,
        total_focus_minutes=total_focus_minutes,
        total_habits_logged=total_habits,
        total_workouts_completed=total_workouts,
        total_sleep_nights_recorded=total_sleep,
        total_resources_collected=ResourcesGained(
            water=total_water, food=total_food, materials=total_materials
        ),
        total_experience_earned=total_xp_earned,
        level_progression=level_progression,
        current_streak_days=_calculate_streak(user_id),
    )
