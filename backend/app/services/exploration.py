"""
Exploration & Skills service.

Reward pipeline contract
------------------------
Exploration outcomes are written as `pending_rewards` rows (is_processed=False)
rather than applied directly to character_stats.  The character module's
POST /character/rewards/process is the single authoritative consumer of all
pending rewards — explorations, focus sessions, habit logs, workouts, and
sleep sessions all flow through the same pipeline.  This keeps the reward
ledger auditable, prevents double-application on retries, and means the
frontend can show a "pending loot" summary before the player chooses to
bank it.

Success-chance cap
------------------
The adventure_impact_score bonus is capped at +40% (impact * 0.01, max 0.40)
so that obsessive task-completion cannot trivialise dangerous areas.  Without
a cap a player with 80+ impact points would have a near-certain 110%+ chance
on extreme areas, removing all risk from high-difficulty content.  The cap
preserves tension at every tier while still meaningfully rewarding productive
real-world behaviour.
"""

import random
from datetime import datetime, timezone
from uuid import UUID

from app.core.supabase_client import get_supabase
from app.schemas.exploration import (
    AdventureEstimateResponse,
    AreaEstimate,
    DiscoveryBreakdown,
    DiscoveryResponse,
    ExplorationAreaResponse,
    ExplorationCompleteResponse,
    ExplorationResponse,
    ExplorationStatsResponse,
    HabitContribution,
    RewardSummary,
    SkillDetailResponse,
    TaskContribution,
)


# ── Errors ─────────────────────────────────────────────────────────────────────


class ServiceError(Exception):
    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Static game data ───────────────────────────────────────────────────────────

SKILL_UNLOCKS: dict[str, dict] = {
    "strength": {
        "description": "Physical power and endurance in hostile environments",
        "unlocks": {
            1: "Basic melee",
            3: "Heavy weapons",
            5: "Fortify camp",
            10: "Legendary strength",
        },
    },
    "endurance": {
        "description": "Ability to sustain long explorations without rest",
        "unlocks": {
            1: "Short runs",
            3: "Extended runs",
            5: "Night explorations",
            10: "Extreme terrain",
        },
    },
    "focus": {
        "description": "Mental clarity to solve problems and craft items",
        "unlocks": {
            1: "Basic crafting",
            3: "Advanced crafting",
            5: "Trap building",
            10: "Master engineer",
        },
    },
    "resilience": {
        "description": "Resistance to disease, injury and psychological stress",
        "unlocks": {
            1: "Faster healing",
            3: "Poison resistance",
            5: "Trauma resistance",
            10: "Immortal will",
        },
    },
    "agility": {
        "description": "Speed, stealth and ability to escape threats",
        "unlocks": {
            1: "Fast travel",
            3: "Stealth runs",
            5: "Ambush attacks",
            10: "Ghost protocol",
        },
    },
    "survival": {
        "description": "Knowledge of the wild, foraging and resource management",
        "unlocks": {
            1: "Basic foraging",
            3: "Water purification",
            5: "Advanced trapping",
            10: "Wasteland master",
        },
    },
}

EXPLORATION_AREAS: list[dict] = [
    {
        "name": "Abandoned Suburb",
        "description": "Quiet streets frozen in time. Houses picked through but not stripped bare.",
        "difficulty": "easy",
        "min_character_level": 1,
        "min_skill_requirements": None,
        "possible_resources": ["water", "food", "materials"],
        "possible_discoveries": ["supply_cache", "survivor_note"],
    },
    {
        "name": "Collapsed Highway",
        "description": "A crumbled overpass spanning a dried riverbed. Useful for ambushes — by you or them.",
        "difficulty": "easy",
        "min_character_level": 1,
        "min_skill_requirements": None,
        "possible_resources": ["materials", "food"],
        "possible_discoveries": ["survivor_note", "map_fragment"],
    },
    {
        "name": "Overrun Supermarket",
        "description": "Food everywhere — if you can get past what moved in.",
        "difficulty": "medium",
        "min_character_level": 3,
        "min_skill_requirements": {"survival": 2},
        "possible_resources": ["food", "water", "materials"],
        "possible_discoveries": ["supply_cache", "blueprint", "survivor_note"],
    },
    {
        "name": "Flooded Hospital",
        "description": "Medical supplies float in dark water. Something else does too.",
        "difficulty": "medium",
        "min_character_level": 4,
        "min_skill_requirements": {"resilience": 2},
        "possible_resources": ["water", "materials"],
        "possible_discoveries": ["medicine_cache", "survivor_note", "safe_house"],
    },
    {
        "name": "Military Checkpoint",
        "description": "Weapons, vehicles, and whatever held the line for three weeks.",
        "difficulty": "hard",
        "min_character_level": 6,
        "min_skill_requirements": {"strength": 3, "agility": 2},
        "possible_resources": ["water", "food", "materials"],
        "possible_discoveries": ["weapon_cache", "supply_cache", "map_fragment"],
    },
    {
        "name": "Downtown Ruins",
        "description": "The city's skeleton. Forty floors of scavenging — or forty floors of ambush.",
        "difficulty": "hard",
        "min_character_level": 7,
        "min_skill_requirements": {"endurance": 3},
        "possible_resources": ["materials", "food", "water"],
        "possible_discoveries": ["blueprint", "supply_cache", "safe_house"],
    },
    {
        "name": "Underground Bunker",
        "description": "Built to last centuries. Someone else found it first.",
        "difficulty": "extreme",
        "min_character_level": 10,
        "min_skill_requirements": {"focus": 4, "survival": 4},
        "possible_resources": ["water", "food", "materials"],
        "possible_discoveries": ["weapon_cache", "medicine_cache", "blueprint", "survivor_note"],
    },
    {
        "name": "The Dead Zone",
        "description": "Ground zero. The radiation is gone but whatever it made is not.",
        "difficulty": "extreme",
        "min_character_level": 15,
        "min_skill_requirements": {"strength": 5, "resilience": 5, "agility": 5},
        "possible_resources": ["materials", "water", "food"],
        "possible_discoveries": ["weapon_cache", "blueprint", "map_fragment", "safe_house"],
    },
]

# Keyed lookup built once at import time.
_AREA_BY_NAME: dict[str, dict] = {a["name"]: a for a in EXPLORATION_AREAS}

# ── Outcome tables ─────────────────────────────────────────────────────────────

_DIFFICULTY_MODIFIER: dict[str, float] = {
    "easy": 0.9,
    "medium": 0.7,
    "hard": 0.5,
    "extreme": 0.3,
}

_DIFFICULTY_XP: dict[str, int] = {
    "easy": 10,
    "medium": 25,
    "hard": 50,
    "extreme": 100,
}

_RESOURCE_RANGES: dict[str, dict[str, tuple[int, int]]] = {
    "easy":    {"water": (2, 5),   "food": (1, 4),   "materials": (0, 2)},
    "medium":  {"water": (4, 8),   "food": (3, 6),   "materials": (1, 4)},
    "hard":    {"water": (6, 12),  "food": (5, 10),  "materials": (3, 6)},
    "extreme": {"water": (10, 20), "food": (8, 15),  "materials": (5, 10)},
}

# ── Discovery pools ────────────────────────────────────────────────────────────

_DISCOVERY_POOL: dict[str, list[dict]] = {
    "supply_cache": [
        {"name": "Abandoned Supply Cache",
         "description": "Sealed boxes of supplies left behind in the chaos."},
        {"name": "Rooftop Stash",
         "description": "Someone cached supplies on the roof. Smart — until it wasn't."},
        {"name": "Buried Footlocker",
         "description": "Covered in dirt but still intact. Someone planned ahead."},
    ],
    "survivor_note": [
        {"name": "Warning Note",
         "description": "A scrawled message: 'Don't go north. NEVER go north.'"},
        {"name": "Survivor's Journal",
         "description": "Days 1 through 12. Day 13 is blank."},
        {"name": "Evacuation Map",
         "description": "A hand-drawn route to a shelter that may or may not still exist."},
        {"name": "Radio Frequency List",
         "description": "Channels and call signs. At least two are still broadcasting."},
    ],
    "map_fragment": [
        {"name": "Torn Topographic Map",
         "description": "Part of a military map. The rest could be anywhere."},
        {"name": "City Grid Fragment",
         "description": "Streets, blocks, and a circled location labelled '?'."},
        {"name": "Annotated Transit Map",
         "description": "Tunnel routes marked with safety ratings. Most say 'avoid'."},
    ],
    "weapon_cache": [
        {"name": "Hidden Armory",
         "description": "Firearms, ammo, and a note: 'For when they come back.'"},
        {"name": "Police Station Arsenal",
         "description": "Whatever the officers didn't take when they fled."},
        {"name": "Militia Stockpile",
         "description": "Crates of weapons from a group that didn't make it."},
    ],
    "medicine_cache": [
        {"name": "Hospital Supply Room",
         "description": "Antibiotics, bandages, and a defibrillator. Jackpot."},
        {"name": "Pharmacy Remnants",
         "description": "Most of it's gone. What's left is still valuable."},
        {"name": "Field Medic Kit",
         "description": "Military-issue trauma kit, still sealed."},
    ],
    "blueprint": [
        {"name": "Generator Schematic",
         "description": "Instructions for building a small generator from scrap."},
        {"name": "Filtration Design",
         "description": "A system for purifying contaminated water. Priceless."},
        {"name": "Fortification Plans",
         "description": "Defensive barrier designs drawn by someone who knew what they were doing."},
        {"name": "Radio Transmitter Blueprint",
         "description": "Long-range communication — if you can find the parts."},
    ],
    "safe_house": [
        {"name": "Fortified Basement",
         "description": "Reinforced walls, a water supply, and a lock that still works."},
        {"name": "Rooftop Refuge",
         "description": "Elevated, defensible, and invisible from street level."},
        {"name": "Underground Hideout",
         "description": "A former maintenance room converted into a livable space."},
    ],
}

_DISCOVERY_RARITY: dict[str, str] = {
    "supply_cache": "common",
    "survivor_note": "common",
    "map_fragment": "uncommon",
    "medicine_cache": "uncommon",
    "safe_house": "uncommon",
    "blueprint": "rare",
    "weapon_cache": "rare",
}


# ── DB helpers ────────────────────────────────────────────────────────────────


def _execute(query):
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _get_character(user_id: str) -> dict:
    sb = get_supabase()
    res = _execute(
        sb.table("characters").select("*").eq("user_id", user_id).limit(1)
    )
    if not res.data:
        raise ServiceError("Character not found.", 404)
    return res.data[0]


def _get_skills_map(character_id: str) -> dict[str, dict]:
    sb = get_supabase()
    res = _execute(
        sb.table("character_skills").select("*").eq("character_id", character_id)
    )
    return {row["skill_name"]: row for row in (res.data or [])}


def _check_area_unlock(area: dict, character: dict, skills: dict[str, dict]) -> bool:
    if character["level"] < area["min_character_level"]:
        return False
    for skill_name, min_level in (area["min_skill_requirements"] or {}).items():
        if (skills.get(skill_name) or {}).get("level", 0) < min_level:
            return False
    return True


def _success_chance(difficulty: str, impact_score: int) -> float:
    base = _DIFFICULTY_MODIFIER[difficulty]
    bonus = min(impact_score * 0.01, 0.40)
    return round(base + bonus, 4)


def _adventure_since(character_id: str, character_created_at: str) -> datetime:
    """Return the datetime after which task completions count toward the next exploration."""
    sb = get_supabase()
    res = _execute(
        sb.table("explorations")
        .select("ended_at")
        .eq("character_id", character_id)
        .not_.is_("ended_at", "null")
        .order("ended_at", desc=True)
        .limit(1)
    )
    if res.data and res.data[0].get("ended_at"):
        return _parse_dt(res.data[0]["ended_at"])
    return _parse_dt(character_created_at)


def _task_contributions(user_id: str, since_dt: datetime) -> tuple[int, list[TaskContribution]]:
    """Sum adventure impact from tasks completed since `since_dt`."""
    sb = get_supabase()
    res = _execute(
        sb.table("tasks")
        .select("title, estimated_adventure_impact, completed_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .gte("completed_at", since_dt.isoformat())
        .not_.is_("estimated_adventure_impact", "null")
        .order("completed_at", desc=True)
    )
    tasks = res.data or []
    total = sum(t.get("estimated_adventure_impact") or 0 for t in tasks)
    contributions = [
        TaskContribution(
            task_title=t.get("title", "Unnamed task"),
            impact=t.get("estimated_adventure_impact") or 0,
            completed_at=t.get("completed_at", ""),
        )
        for t in tasks
    ]
    return total, contributions


def _fetch_exploration(character_id: str, exploration_id: str) -> dict:
    sb = get_supabase()
    res = _execute(
        sb.table("explorations")
        .select("*")
        .eq("id", exploration_id)
        .eq("character_id", character_id)
        .limit(1)
    )
    if not res.data:
        raise ServiceError("Exploration not found.", 404)
    return res.data[0]


def _fetch_discoveries(exploration_id: str) -> list[dict]:
    sb = get_supabase()
    res = _execute(
        sb.table("exploration_discoveries")
        .select("*")
        .eq("exploration_id", exploration_id)
        .order("created_at")
    )
    return res.data or []


def _build_exploration_response(expl: dict, include_discoveries: bool = False) -> ExplorationResponse:
    discoveries: list[DiscoveryResponse] = []
    if include_discoveries:
        raw = _fetch_discoveries(expl["id"])
        discoveries = [DiscoveryResponse.model_validate(d) for d in raw]
    return ExplorationResponse(**{k: v for k in expl for k, v in [(k, expl[k])]}, discoveries=discoveries)


def _insert_pending_reward(
    character_id: str,
    experience_points: int,
    resources: dict,
) -> None:
    sb = get_supabase()
    _execute(
        sb.table("pending_rewards").insert(
            {
                "character_id": character_id,
                "source_type": "exploration",
                "health_delta": 0,
                "energy_delta": 0,
                "experience_points": experience_points,
                "resources": resources,
                "skill_rewards": {},
                "is_processed": False,
            }
        )
    )


# ── Skills ────────────────────────────────────────────────────────────────────


def _build_skill_detail(
    user_id: str, character_id: str, skill_row: dict
) -> SkillDetailResponse:
    sname = skill_row["skill_name"]
    level = skill_row["level"]
    pts = skill_row["current_points"]
    pts_needed = skill_row["points_to_next_level"]

    progress_pct = round((pts / pts_needed * 100), 1) if pts_needed > 0 else 0.0

    meta = SKILL_UNLOCKS.get(sname, {"description": "", "unlocks": {}})
    all_unlocks: dict[int, str] = meta.get("unlocks", {})

    current_unlocks = [v for k, v in sorted(all_unlocks.items()) if k <= level]
    next_unlock = next((v for k, v in sorted(all_unlocks.items()) if k > level), None)

    # Total points ever earned — sum skill_rewards[sname] across processed rewards
    sb = get_supabase()
    rewards_res = _execute(
        sb.table("pending_rewards")
        .select("skill_rewards")
        .eq("character_id", character_id)
        .eq("is_processed", True)
    )
    total_ever = sum(
        (row.get("skill_rewards") or {}).get(sname, 0) or 0
        for row in (rewards_res.data or [])
    )

    # Contributing active habits via habit_skills join
    habits_res = _execute(
        sb.table("habits")
        .select("id, name, habit_skills(skill_name, points_per_completion)")
        .eq("user_id", user_id)
        .eq("is_active", True)
    )
    contributing: list[HabitContribution] = []
    for habit in habits_res.data or []:
        for hs in habit.get("habit_skills") or []:
            if hs["skill_name"] == sname:
                contributing.append(
                    HabitContribution(
                        habit_id=habit["id"],
                        habit_name=habit["name"],
                        skill_name=sname,
                        points_per_completion=hs["points_per_completion"],
                    )
                )

    return SkillDetailResponse(
        skill_name=sname,
        level=level,
        current_points=pts,
        points_to_next_level=pts_needed,
        progress_percentage=progress_pct,
        description=meta.get("description", ""),
        current_unlocks=current_unlocks,
        next_unlock=next_unlock,
        total_points_ever_earned=total_ever,
        contributing_habits=contributing,
    )


def get_skills(user_id: str) -> list[SkillDetailResponse]:
    character = _get_character(user_id)
    cid = character["id"]
    skills = _get_skills_map(cid)
    return [_build_skill_detail(user_id, cid, s) for s in skills.values()]


def get_skill(user_id: str, skill_name: str) -> SkillDetailResponse:
    if skill_name not in SKILL_UNLOCKS:
        raise ServiceError(f"Unknown skill: '{skill_name}'.", 404)
    character = _get_character(user_id)
    cid = character["id"]
    skills = _get_skills_map(cid)
    skill_row = skills.get(skill_name)
    if not skill_row:
        raise ServiceError(f"Skill '{skill_name}' not found for this character.", 404)
    return _build_skill_detail(user_id, cid, skill_row)


# ── Areas ─────────────────────────────────────────────────────────────────────


def get_areas(user_id: str) -> list[ExplorationAreaResponse]:
    character = _get_character(user_id)
    cid = character["id"]
    skills = _get_skills_map(cid)
    return [
        ExplorationAreaResponse(
            **{k: v for k, v in area.items()},
            is_unlocked=_check_area_unlock(area, character, skills),
        )
        for area in EXPLORATION_AREAS
    ]


# ── Exploration CRUD ──────────────────────────────────────────────────────────


def list_explorations(user_id: str) -> list[ExplorationResponse]:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]
    res = _execute(
        sb.table("explorations")
        .select("*")
        .eq("character_id", cid)
        .order("started_at", desc=True)
    )
    return [ExplorationResponse.model_validate(e) for e in (res.data or [])]


def get_exploration(user_id: str, exploration_id: str) -> ExplorationResponse:
    character = _get_character(user_id)
    expl = _fetch_exploration(character["id"], exploration_id)
    raw_disc = _fetch_discoveries(exploration_id)
    expl_resp = ExplorationResponse.model_validate(expl)
    expl_resp.discoveries = [DiscoveryResponse.model_validate(d) for d in raw_disc]
    return expl_resp


def get_discoveries(user_id: str) -> list[DiscoveryResponse]:
    sb = get_supabase()
    character = _get_character(user_id)
    res = _execute(
        sb.table("exploration_discoveries")
        .select("*")
        .eq("character_id", character["id"])
        .order("created_at", desc=True)
    )
    return [DiscoveryResponse.model_validate(d) for d in (res.data or [])]


# ── Exploration mutations ─────────────────────────────────────────────────────


def start_exploration(user_id: str, area_name: str) -> ExplorationResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    # Character must be alive
    if not character.get("is_alive", True):
        raise ServiceError("Character is dead and cannot start an exploration.", 400)

    # Validate area
    area = _AREA_BY_NAME.get(area_name)
    if not area:
        raise ServiceError(f"Unknown area: '{area_name}'.", 404)

    # No concurrent explorations
    active_res = _execute(
        sb.table("explorations")
        .select("id")
        .eq("character_id", cid)
        .eq("status", "in_progress")
        .limit(1)
    )
    if active_res.data:
        raise ServiceError(
            "An exploration is already in progress. Complete or fail it before starting another.",
            409,
        )

    # Unlock check
    skills = _get_skills_map(cid)
    if not _check_area_unlock(area, character, skills):
        missing: list[str] = []
        if character["level"] < area["min_character_level"]:
            missing.append(
                f"character level {area['min_character_level']} (current: {character['level']})"
            )
        for sname, min_lvl in (area.get("min_skill_requirements") or {}).items():
            current_lvl = (skills.get(sname) or {}).get("level", 0)
            if current_lvl < min_lvl:
                missing.append(f"{sname} level {min_lvl} (current: {current_lvl})")
        raise ServiceError(
            f"Area locked. Requirements not met: {'; '.join(missing)}.", 403
        )

    # Energy check
    stats_res = _execute(
        sb.table("character_stats")
        .select("energy, max_energy")
        .eq("character_id", cid)
        .limit(1)
    )
    if not stats_res.data or stats_res.data[0]["energy"] < 20:
        raise ServiceError(
            "Not enough energy to start an exploration (minimum 20 required).", 400
        )

    # Calculate adventure impact score
    since_dt = _adventure_since(cid, character["created_at"])
    impact_score, _ = _task_contributions(user_id, since_dt)

    # Deduct 10 energy
    current_energy = stats_res.data[0]["energy"]
    _execute(
        sb.table("character_stats")
        .update({"energy": max(0, current_energy - 10)})
        .eq("character_id", cid)
    )

    # Create exploration row
    now = _now_iso()
    expl_res = _execute(
        sb.table("explorations")
        .insert(
            {
                "character_id": cid,
                "area_name": area_name,
                "difficulty": area["difficulty"],
                "status": "in_progress",
                "adventure_impact_score": impact_score,
                "started_at": now,
            }
        )
        .select()
    )
    return ExplorationResponse.model_validate(expl_res.data[0])


def complete_exploration(user_id: str, exploration_id: str) -> ExplorationCompleteResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    expl = _fetch_exploration(cid, exploration_id)
    if expl["status"] != "in_progress":
        raise ServiceError(
            f"Exploration is not in progress (current status: '{expl['status']}').", 400
        )

    difficulty: str = expl["difficulty"]
    impact_score: int = expl.get("adventure_impact_score") or 0

    chance = _success_chance(difficulty, impact_score)
    was_successful = random.random() < chance

    diff_xp = _DIFFICULTY_XP[difficulty]
    discoveries_data: list[dict] = []

    if was_successful:
        rng = _RESOURCE_RANGES[difficulty]
        resources_found: dict | None = {
            "water":     random.randint(*rng["water"]),
            "food":      random.randint(*rng["food"]),
            "materials": random.randint(*rng["materials"]),
        }
        experience_earned = impact_score + diff_xp

        # Generate 1–3 discoveries from this area's pool
        area = _AREA_BY_NAME.get(expl["area_name"], {})
        disc_types_available: list[str] = area.get("possible_discoveries") or ["supply_cache"]
        num_disc = random.randint(1, min(3, len(disc_types_available)))
        chosen_types = random.choices(disc_types_available, k=num_disc)

        for dtype in chosen_types:
            pool = _DISCOVERY_POOL.get(dtype) or [
                {"name": "Mysterious Find", "description": "Something unexpected in the ruins."}
            ]
            pick = random.choice(pool)
            discoveries_data.append(
                {
                    "exploration_id": exploration_id,
                    "character_id": cid,
                    "discovery_type": dtype,
                    "name": pick["name"],
                    "description": pick["description"],
                    "rarity": _DISCOVERY_RARITY.get(dtype, "common"),
                }
            )
    else:
        resources_found = None
        experience_earned = int(diff_xp * 0.25)

    now = _now_iso()
    _execute(
        sb.table("explorations")
        .update(
            {
                "status": "completed",
                "ended_at": now,
                "was_successful": was_successful,
                "resources_found": resources_found,
                "experience_earned": experience_earned,
            }
        )
        .eq("id", exploration_id)
    )

    # Insert discoveries
    inserted: list[dict] = []
    if discoveries_data:
        disc_res = _execute(
            sb.table("exploration_discoveries").insert(discoveries_data).select()
        )
        inserted = disc_res.data or []

    # Queue reward for the character pipeline
    _insert_pending_reward(
        character_id=cid,
        experience_points=experience_earned,
        resources=resources_found or {},
    )

    # Re-fetch final exploration state
    updated = _execute(
        sb.table("explorations").select("*").eq("id", exploration_id).limit(1)
    ).data[0]

    return ExplorationCompleteResponse(
        exploration=ExplorationResponse.model_validate(updated),
        discoveries=[DiscoveryResponse.model_validate(d) for d in inserted],
        reward_summary=RewardSummary(
            experience_earned=experience_earned,
            resources_found=resources_found,
            discoveries_count=len(inserted),
            pending_reward_created=True,
        ),
        success_chance=chance,
        was_successful=was_successful,
    )


def fail_exploration(user_id: str, exploration_id: str) -> ExplorationResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    expl = _fetch_exploration(cid, exploration_id)
    if expl["status"] != "in_progress":
        raise ServiceError(
            f"Exploration is not in progress (current status: '{expl['status']}').", 400
        )

    now = _now_iso()
    _execute(
        sb.table("explorations")
        .update(
            {
                "status": "failed",
                "ended_at": now,
                "was_successful": False,
                "resources_found": None,
                "experience_earned": 0,
            }
        )
        .eq("id", exploration_id)
    )

    updated = _execute(
        sb.table("explorations").select("*").eq("id", exploration_id).limit(1)
    ).data[0]
    return ExplorationResponse.model_validate(updated)


# ── Stats & estimate ──────────────────────────────────────────────────────────


def get_stats(user_id: str) -> ExplorationStatsResponse:
    sb = get_supabase()
    character = _get_character(user_id)
    cid = character["id"]

    expl_res = _execute(
        sb.table("explorations")
        .select("id, area_name, status, was_successful, resources_found, experience_earned")
        .eq("character_id", cid)
    )
    explorations: list[dict] = expl_res.data or []

    total = len(explorations)
    total_successful = sum(1 for e in explorations if e.get("was_successful") is True)
    total_failed = sum(1 for e in explorations if e.get("was_successful") is False)
    success_rate = round(total_successful / total * 100, 1) if total else 0.0

    total_resources: dict[str, int] = {"water": 0, "food": 0, "materials": 0}
    total_xp = 0
    area_counts: dict[str, int] = {}
    best_id: str | None = None
    best_total = -1

    for expl in explorations:
        r: dict = expl.get("resources_found") or {}
        r_sum = sum(r.get(k, 0) or 0 for k in ("water", "food", "materials"))
        for k in ("water", "food", "materials"):
            total_resources[k] += r.get(k, 0) or 0
        total_xp += expl.get("experience_earned") or 0

        area = expl.get("area_name") or "Unknown"
        area_counts[area] = area_counts.get(area, 0) + 1

        if r_sum > best_total:
            best_total = r_sum
            best_id = expl["id"]

    favourite_area = max(area_counts, key=area_counts.__getitem__) if area_counts else None

    disc_res = _execute(
        sb.table("exploration_discoveries")
        .select("discovery_type")
        .eq("character_id", cid)
    )
    disc_counts: dict[str, int] = {}
    for row in disc_res.data or []:
        dt = row.get("discovery_type", "unknown")
        disc_counts[dt] = disc_counts.get(dt, 0) + 1

    return ExplorationStatsResponse(
        total_attempted=total,
        total_successful=total_successful,
        total_failed=total_failed,
        success_rate_pct=success_rate,
        total_resources_found=total_resources,
        total_experience_earned=total_xp,
        discoveries_by_type=[
            DiscoveryBreakdown(discovery_type=k, count=v)
            for k, v in sorted(disc_counts.items())
        ],
        favourite_area=favourite_area,
        best_exploration_id=UUID(best_id) if best_id else None,
    )


def get_adventure_estimate(user_id: str) -> AdventureEstimateResponse:
    character = _get_character(user_id)
    cid = character["id"]
    skills = _get_skills_map(cid)

    since_dt = _adventure_since(cid, character["created_at"])
    impact_score, contributions = _task_contributions(user_id, since_dt)

    area_estimates: list[AreaEstimate] = []
    for area in EXPLORATION_AREAS:
        unlocked = _check_area_unlock(area, character, skills)
        chance = _success_chance(area["difficulty"], impact_score)
        area_estimates.append(
            AreaEstimate(
                area_name=area["name"],
                difficulty=area["difficulty"],
                success_chance=chance,
                is_unlocked=unlocked,
            )
        )

    return AdventureEstimateResponse(
        current_impact_score=impact_score,
        task_contributions=contributions,
        area_estimates=area_estimates,
    )
