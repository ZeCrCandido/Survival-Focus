"""
Apple Health JSON sleep parser.

Public API:
    parse_sleep_entry(raw: dict) -> ParsedSleepEntry

Safe-access strategy
────────────────────
Every field is extracted with .get() and a typed cast helper. None / 0.0
are canonical "absent or unparseable" values — never errors.

The *only* exceptions raised by parse_sleep_entry() are ValueError for
truly unrecoverable data:
    • missing "date" field
    • sleepStart or sleepEnd cannot be parsed
    • totalSleep is 0 or missing (corrupt record)

The caller (import endpoint) wraps each call in try/except and increments
a failure counter, so one bad entry never aborts the entire batch import.

Sleep quality scoring
─────────────────────
_calculate_sleep_quality() is a Python mirror of the Postgres function
public.calculate_sleep_quality() defined in supabase/migrations/sleep.sql.
Both apply identical thresholds so results are deterministic regardless of
which side computes the label.  The Python fallback is used at import time
to avoid an extra round-trip to the database.

Datetime handling
─────────────────
Apple Health exports timestamps in the format "2026-05-07 01:31:00 +0100".
Every timestamp is parsed and normalised to UTC before storage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Output type ───────────────────────────────────────────────────────────────


@dataclass
class ParsedSleepEntry:
    external_date:        str              # "YYYY-MM-DD"
    source:               str
    sleep_start:          datetime         # UTC-normalised
    sleep_end:            datetime         # UTC-normalised
    in_bed_start:         datetime         # UTC-normalised
    in_bed_end:           datetime         # UTC-normalised
    total_sleep_hours:    float
    total_sleep_minutes:  int
    rem_hours:            float
    rem_minutes:          int
    deep_hours:           float
    deep_minutes:         int
    core_hours:           float
    core_minutes:         int
    awake_hours:          float
    awake_minutes:        int
    sleep_quality:        str              # poor | fair | good | excellent
    raw_data:             dict = field(default_factory=dict)


# ── Datetime parsing ──────────────────────────────────────────────────────────

_DT_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S %z",    # Apple Health primary: "2026-05-07 01:31:00 +0100"
    "%Y-%m-%dT%H:%M:%S%z",     # ISO 8601 compact:     "2026-05-07T01:31:00+01:00"
    "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO 8601 microseconds
)


def _parse_dt(value: Any) -> datetime | None:
    """
    Try every known Apple Health datetime format in order.
    Returns a UTC-aware datetime, or None on any failure.  Never raises.
    """
    if not value or not isinstance(value, str):
        return None
    v = value.strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(v, fmt).astimezone(timezone.utc)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


# ── Scalar cast helpers ───────────────────────────────────────────────────────


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Cast to float or return default.  Never raises."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ── Sleep quality scoring (mirrors Postgres calculate_sleep_quality()) ────────


def _calculate_sleep_quality(
    total_sleep_hours: float,
    deep_hours: float,
    rem_hours: float,
) -> str:
    """
    Python-side mirror of public.calculate_sleep_quality() in sleep.sql.

    Scoring:
      Base (total sleep): <5→0 | 5–5.9→1 | 6–6.9→2 | 7–8.9→3 | ≥9→2
      Deep ratio:         <0.10→0 | 0.10–0.19→1 | ≥0.20→2
      REM  ratio:         <0.15→0 | 0.15–0.24→1 | ≥0.25→2
      Total → enum:       0–2→poor | 3–4→fair | 5–6→good | 7→excellent

    Must stay byte-for-byte equivalent to the SQL logic so that the
    sleep_quality label is identical whether it is computed at import time
    (Python) or recalculated from a stored session (Postgres).
    """
    if total_sleep_hours <= 0:
        return "poor"

    # Base score — duration
    if total_sleep_hours < 5.0:
        base = 0
    elif total_sleep_hours < 6.0:
        base = 1
    elif total_sleep_hours < 7.0:
        base = 2
    elif total_sleep_hours < 9.0:
        base = 3
    else:                         # ≥ 9 h (oversleeping)
        base = 2

    # Deep-sleep ratio score
    deep_ratio = deep_hours / total_sleep_hours
    if deep_ratio < 0.10:
        deep_score = 0
    elif deep_ratio < 0.20:
        deep_score = 1
    else:
        deep_score = 2

    # REM-sleep ratio score
    rem_ratio = rem_hours / total_sleep_hours
    if rem_ratio < 0.15:
        rem_score = 0
    elif rem_ratio < 0.25:
        rem_score = 1
    else:
        rem_score = 2

    total = base + deep_score + rem_score
    if total <= 2:
        return "poor"
    if total <= 4:
        return "fair"
    if total <= 6:
        return "good"
    return "excellent"


# ── Public API ────────────────────────────────────────────────────────────────


def parse_sleep_entry(raw: dict) -> ParsedSleepEntry:
    """
    Convert one Apple Health sleep JSON object into a ParsedSleepEntry.

    Raises ValueError only for truly unrecoverable data:
        • "date" field is absent or empty
        • sleepStart or sleepEnd cannot be parsed
        • totalSleep is 0 or missing (corrupt / incomplete record)

    All other field failures degrade gracefully to 0.0 so the import loop
    counts them as partial successes rather than hard failures.

    Usage:
        try:
            entry = parse_sleep_entry(raw_dict)
        except ValueError as exc:
            # count as failed, continue to next entry
    """
    if not isinstance(raw, dict):
        raise ValueError("Sleep entry is not a JSON object.")

    # ── Required: date ───────────────────────────────────────────────────────
    raw_date = str(raw.get("date") or "").strip()
    if not raw_date:
        raise ValueError("Sleep entry is missing the 'date' field.")
    external_date = raw_date[:10]  # keep only "YYYY-MM-DD"

    # ── Required: timestamps ─────────────────────────────────────────────────
    sleep_start = _parse_dt(raw.get("sleepStart"))
    sleep_end   = _parse_dt(raw.get("sleepEnd"))
    if sleep_start is None or sleep_end is None:
        raise ValueError(
            f"Cannot parse sleepStart/sleepEnd for date={external_date!r}."
        )

    # in_bed timestamps fall back to sleep timestamps when absent
    in_bed_start = _parse_dt(raw.get("inBedStart")) or sleep_start
    in_bed_end   = _parse_dt(raw.get("inBedEnd"))   or sleep_end

    # ── Required: total sleep (reject corrupt entries) ───────────────────────
    total_sleep_hours = _safe_float(raw.get("totalSleep"))
    if total_sleep_hours <= 0:
        raise ValueError(
            f"totalSleep is 0 or missing for date={external_date!r} — "
            "skipping corrupt entry."
        )

    # ── Phase durations (all optional, default 0.0) ──────────────────────────
    rem_hours   = _safe_float(raw.get("rem"))
    deep_hours  = _safe_float(raw.get("deep"))
    core_hours  = _safe_float(raw.get("core"))
    awake_hours = _safe_float(raw.get("awake"))

    sleep_quality = _calculate_sleep_quality(total_sleep_hours, deep_hours, rem_hours)

    return ParsedSleepEntry(
        external_date=       external_date,
        source=              str(raw.get("source") or "apple_health").strip(),
        sleep_start=         sleep_start,
        sleep_end=           sleep_end,
        in_bed_start=        in_bed_start,
        in_bed_end=          in_bed_end,
        total_sleep_hours=   total_sleep_hours,
        total_sleep_minutes= round(total_sleep_hours * 60),
        rem_hours=           rem_hours,
        rem_minutes=         round(rem_hours * 60),
        deep_hours=          deep_hours,
        deep_minutes=        round(deep_hours * 60),
        core_hours=          core_hours,
        core_minutes=        round(core_hours * 60),
        awake_hours=         awake_hours,
        awake_minutes=       round(awake_hours * 60),
        sleep_quality=       sleep_quality,
        raw_data=            raw,
    )
