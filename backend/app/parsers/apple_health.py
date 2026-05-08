"""
Apple Health JSON workout parser.

Public API:
    parse_workout(raw: dict) -> ParsedWorkout

Safe-access strategy
────────────────────
Every field is extracted through a chain of .get() calls and a typed
cast helper (_safe_float / _safe_int / _safe_str).  None is the
canonical "field absent or unparseable" value — it is never an error.

The *only* exceptions raised by parse_workout() are ValueError for
truly unrecoverable data (missing or unparseable start/end timestamps,
zero or negative duration).  The caller (import endpoint) wraps each
call in try/except and counts failures, so one bad workout never
aborts the entire import.

Granular array reductions
─────────────────────────
heartRateData[], stepCount[], and activeEnergy[] each contain one
entry per minute of the workout.  They are reduced as follows:

    min_heart_rate      ← MIN of every entry's ".Min" key
    total_steps         ← SUM of every entry's ".qty" key  (→ int)
    total_active_energy ← SUM of every entry's ".qty" key  (kcal)

These aggregate values may differ from the top-level summary fields
(avgHeartRate, activeEnergyBurned) because Apple computes top-level
values using its own smoothing and sensor-fusion algorithms, whereas
the per-minute arrays reflect raw sensor readings.  The service layer
decides which value to store (see services/workouts.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Output type ───────────────────────────────────────────────────────────────


@dataclass
class ParsedWorkout:
    # ── Required
    external_id:         str
    name:                str
    started_at:          datetime        # UTC-normalised
    ended_at:            datetime        # UTC-normalised
    duration_seconds:    int
    source:              str = "apple_health"
    # ── Movement
    distance_km:         float | None = None
    avg_speed_kmh:       float | None = None
    step_cadence:        float | None = None
    total_steps:         int   | None = None
    elevation_up_meters: float | None = None
    # ── Energy
    active_energy_kcal:  float | None = None
    intensity:           float | None = None
    # ── Heart rate
    avg_heart_rate:      float | None = None
    max_heart_rate:      int   | None = None
    min_heart_rate:      int   | None = None  # from granular array
    # ── Environment
    temperature_celsius: float | None = None
    humidity_percent:    float | None = None
    # ── Derived
    effort_level:        str   | None = None
    # ── Granular array totals (retained for cross-validation)
    total_active_energy: float | None = None
    # ── Raw source preserved for re-parsing
    raw_data:            dict = field(default_factory=dict)


# ── Datetime parsing ──────────────────────────────────────────────────────────

# Ordered from most-specific to least-specific so the first match wins.
_DT_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S %z",    # Apple Health primary: "2026-04-30 15:59:58 +0100"
    "%Y-%m-%dT%H:%M:%S%z",     # ISO 8601 compact:     "2026-04-30T15:59:58+0100"
    "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO 8601 microseconds: "…T15:59:58.123456+0100"
)


def _parse_dt(value: Any) -> datetime | None:
    """
    Try every known Apple Health datetime format in order.
    Returns a UTC-aware datetime, or None on any failure.
    Never raises.
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(v, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    # Last-resort: let the stdlib fromisoformat handle edge cases
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


# ── Scalar cast helpers ───────────────────────────────────────────────────────


def _safe_float(value: Any) -> float | None:
    """Cast to float or return None. Never raises."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    """Cast via float→int (handles '1628.08') or return None. Never raises."""
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _qty(obj: Any) -> Any:
    """
    Extract the 'qty' key from a metric sub-object, e.g.:
        {"qty": 1.824, "units": "km"}  →  1.824
    Returns None for anything that is not a dict or lacks 'qty'.
    """
    if isinstance(obj, dict):
        return obj.get("qty")
    return None


# ── Effort level (mirrors calculate_effort_level() Postgres function) ─────────


def _effort_level(avg_hr: float | None) -> str | None:
    """
    Python-side effort classification.  Kept in sync with the Postgres
    calculate_effort_level() function defined in migration 005.

    Zones (bpm):
        < 100   → light
        100–129 → moderate
        130–159 → hard
        ≥ 160   → max
    """
    if avg_hr is None:
        return None
    if avg_hr < 100:
        return "light"
    if avg_hr < 130:
        return "moderate"
    if avg_hr < 160:
        return "hard"
    return "max"


# ── Granular array reducers ───────────────────────────────────────────────────


def _min_from_hr_data(hr_data: Any) -> int | None:
    """
    Return MIN of all heartRateData[].Min values.
    Each entry looks like: {"date": "…", "Min": 117, "Avg": 118.5, "Max": 120}
    Skips entries that are missing, non-dict, or contain non-numeric Min.
    Returns None when the array is absent, empty, or yields no valid readings.
    """
    if not isinstance(hr_data, list) or not hr_data:
        return None
    mins: list[float] = []
    for entry in hr_data:
        if not isinstance(entry, dict):
            continue
        v = _safe_float(entry.get("Min"))
        if v is not None:
            mins.append(v)
    return int(min(mins)) if mins else None


def _sum_step_count(step_data: Any) -> int | None:
    """
    Return SUM of all stepCount[].qty values, rounded to the nearest integer.
    Each entry looks like: {"date": "…", "qty": 80.83}
    Returns None when the array is absent, empty, or yields no valid readings.
    """
    if not isinstance(step_data, list) or not step_data:
        return None
    total = 0.0
    found_any = False
    for entry in step_data:
        if not isinstance(entry, dict):
            continue
        v = _safe_float(entry.get("qty"))
        if v is not None:
            total += v
            found_any = True
    return round(total) if found_any else None


def _sum_active_energy(energy_data: Any) -> float | None:
    """
    Return SUM of all activeEnergy[].qty values (kcal).
    Each entry looks like: {"date": "…", "qty": 2.09}
    Returns None when the array is absent, empty, or yields no valid readings.
    """
    if not isinstance(energy_data, list) or not energy_data:
        return None
    total = 0.0
    found_any = False
    for entry in energy_data:
        if not isinstance(entry, dict):
            continue
        v = _safe_float(entry.get("qty"))
        if v is not None:
            total += v
            found_any = True
    return round(total, 4) if found_any else None


# ── Public API ────────────────────────────────────────────────────────────────


def parse_workout(raw: dict) -> ParsedWorkout:
    """
    Convert one Apple Health workout JSON object into a ParsedWorkout.

    Raises ValueError only for truly unrecoverable data:
        • started_at or ended_at cannot be parsed
        • duration is missing, zero, or negative

    All other field failures degrade gracefully to None so the import
    loop can count them as partial successes rather than hard failures.

    Usage:
        try:
            pw = parse_workout(raw_workout_dict)
        except ValueError as exc:
            # count as failed, continue to next workout
    """
    if not isinstance(raw, dict):
        raise ValueError("Workout entry is not a JSON object.")

    # ── Required fields (failure → ValueError, counted as failed import) ───────

    started_at = _parse_dt(raw.get("start"))
    ended_at   = _parse_dt(raw.get("end"))
    if started_at is None or ended_at is None:
        raise ValueError(
            f"Cannot parse start/end for workout id={raw.get('id', '?')!r}"
        )

    duration_seconds = _safe_int(raw.get("duration"))
    if not duration_seconds or duration_seconds <= 0:
        raise ValueError(
            f"Invalid or missing duration for workout id={raw.get('id', '?')!r}"
        )

    # ── Top-level scalar metrics — every access is guarded ────────────────────
    # Pattern: _safe_float(_qty(raw.get("fieldName")))
    # • raw.get() → None if key absent
    # • _qty()    → None if value is not a {"qty": ...} dict
    # • _safe_float/_safe_int → None if qty is not numeric

    avg_hr   = _safe_float(_qty(raw.get("avgHeartRate")))
    max_hr   = _safe_int  (_qty(raw.get("maxHeartRate")))
    dist     = _safe_float(_qty(raw.get("distance")))
    energy   = _safe_float(_qty(raw.get("activeEnergyBurned")))
    speed    = _safe_float(_qty(raw.get("speed")))
    cadence  = _safe_float(_qty(raw.get("stepCadence")))
    temp     = _safe_float(_qty(raw.get("temperature")))
    humidity = _safe_float(_qty(raw.get("humidity")))
    elev     = _safe_float(_qty(raw.get("elevationUp")))
    intens   = _safe_float(_qty(raw.get("intensity")))

    # ── Granular array reductions ──────────────────────────────────────────────
    min_hr              = _min_from_hr_data(raw.get("heartRateData"))
    total_steps         = _sum_step_count(raw.get("stepCount"))
    total_active_energy = _sum_active_energy(raw.get("activeEnergy"))

    # external_id: empty string → None (handled downstream by the service)
    ext_id = str(raw.get("id") or "").strip() or ""

    return ParsedWorkout(
        external_id=         ext_id,
        name=                str(raw.get("name") or "Unknown Workout").strip(),
        started_at=          started_at,
        ended_at=            ended_at,
        duration_seconds=    duration_seconds,
        distance_km=         dist,
        active_energy_kcal=  energy,
        avg_heart_rate=      avg_hr,
        max_heart_rate=      max_hr,
        min_heart_rate=      min_hr,
        avg_speed_kmh=       speed,
        step_cadence=        cadence,
        total_steps=         total_steps,
        temperature_celsius= temp,
        humidity_percent=    humidity,
        elevation_up_meters= elev,
        intensity=           intens,
        effort_level=        _effort_level(avg_hr),
        total_active_energy= total_active_energy,
        raw_data=            raw,
    )
