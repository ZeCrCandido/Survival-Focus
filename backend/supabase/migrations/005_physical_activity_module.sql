
CREATE TYPE public.workout_effort_level AS ENUM (
    'light',     -- < 100 bpm   — gentle movement, warm-up, cool-down
    'moderate',  -- 100–129 bpm — aerobic base, fat-burning zone
    'hard',      -- 130–159 bpm — threshold / tempo work
    'max'        -- ≥ 160 bpm   — anaerobic / high-intensity intervals
);

-- The metric a workout goal tracks.
CREATE TYPE public.workout_goal_type AS ENUM (
    'distance_km',         -- total kilometres covered
    'active_energy_kcal',  -- active calories burned
    'duration_minutes',    -- total time exercising
    'session_count'        -- number of workout sessions
);

-- How often the goal resets.
CREATE TYPE public.workout_goal_period AS ENUM (
    'daily',
    'weekly',
    'monthly'
);




CREATE TABLE public.workout_sessions (
    id                  uuid                        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid                        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

 
    external_id         text,

    name                text                        NOT NULL,

    
    source              text                        NOT NULL DEFAULT 'apple_health',

    
    started_at          timestamptz                 NOT NULL,
    ended_at            timestamptz                 NOT NULL,

    duration_seconds    integer                     NOT NULL CHECK (duration_seconds > 0),

    CONSTRAINT workout_sessions_valid_time
        CHECK (ended_at > started_at),

    distance_km         numeric(8,3),               -- distance.qty, units normalised to km
    avg_speed_kmh       numeric(6,2),               -- speed.qty, units normalised to km/hr
    step_cadence        numeric(6,2),               -- stepCadence.qty  (count/min)
    total_steps         integer,
    elevation_up_meters numeric(7,2),               -- elevationUp.qty, units normalised to m

    active_energy_kcal  numeric(8,2),               -- activeEnergyBurned.qty
    intensity           numeric(6,3),               -- intensity.qty

    avg_heart_rate      numeric(6,2),               -- avgHeartRate.qty
    max_heart_rate      integer,                    -- maxHeartRate.qty
    min_heart_rate      integer,

    temperature_celsius numeric(5,2),               -- temperature.qty, normalised to °C
    humidity_percent    numeric(5,2),               -- humidity.qty  (%)
    effort_level        public.workout_effort_level,

    raw_data            jsonb,

    character_impact    jsonb,
    is_processed        boolean                     NOT NULL DEFAULT false,
    processed_at        timestamptz,

    created_at          timestamptz                 NOT NULL DEFAULT now(),
    updated_at          timestamptz                 NOT NULL DEFAULT now()
);

-- Table & column documentation
COMMENT ON TABLE  public.workout_sessions
    IS 'One consolidated row per workout. Granular per-minute arrays from the '
       'source JSON are aggregated by FastAPI before insert.';

COMMENT ON COLUMN public.workout_sessions.external_id
    IS 'Source-system UUID (e.g. Apple Health). Uniqueness enforced by partial '
       'index when NOT NULL. NULL for manually-entered sessions.';

COMMENT ON COLUMN public.workout_sessions.min_heart_rate
    IS 'MIN of heartRateData[].Min across all per-minute entries. '
       'Not available in the top-level JSON; computed by the FastAPI parser.';

COMMENT ON COLUMN public.workout_sessions.total_steps
    IS 'SUM of stepCount[].qty across all per-minute entries. '
       'More accurate than any single top-level step count.';

COMMENT ON COLUMN public.workout_sessions.raw_data
    IS 'Full original workout JSON object (including granular arrays). '
       'Retained so future metrics can be derived without a re-import.';

COMMENT ON COLUMN public.workout_sessions.character_impact
    IS 'JSONB: { health_delta, energy_delta, '
       'pending_rewards: { xp, source, processed } }. '
       'Set by FastAPI on import; consumed by the character module.';

COMMENT ON COLUMN public.workout_sessions.is_processed
    IS 'False until the character module has applied this session''s '
       'character_impact to the character sheet.';

CREATE UNIQUE INDEX uq_workout_sessions_user_external
    ON public.workout_sessions(user_id, external_id)
    WHERE external_id IS NOT NULL;

CREATE TRIGGER workout_sessions_updated_at
    BEFORE UPDATE ON public.workout_sessions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



CREATE TABLE public.workout_goals (
    id           uuid                        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid                        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    goal_type    public.workout_goal_type    NOT NULL,
    period       public.workout_goal_period  NOT NULL,
    -- The numeric target.  Units depend on goal_type:
    --   distance_km         → kilometres
    --   active_energy_kcal  → kilocalories
    --   duration_minutes    → minutes
    --   session_count       → number of sessions
    target_value numeric                     NOT NULL CHECK (target_value > 0),
    created_at   timestamptz                 NOT NULL DEFAULT now(),
    updated_at   timestamptz                 NOT NULL DEFAULT now(),
    -- One goal per (type, period) per user.
    -- e.g. only one "weekly distance_km" goal at a time.
    UNIQUE (user_id, goal_type, period)
);

COMMENT ON TABLE  public.workout_goals
    IS 'User-defined fitness goals. One goal allowed per (user, goal_type, period) combination.';

COMMENT ON COLUMN public.workout_goals.target_value
    IS 'Numeric target. Unit implied by goal_type: km, kcal, minutes, or session count.';

CREATE TRIGGER workout_goals_updated_at
    BEFORE UPDATE ON public.workout_goals
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



CREATE TABLE public.workout_notes (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- user_id is stored directly (denormalised) so RLS can filter on
    -- a local column rather than joining to workout_sessions on every
    -- read — the same pattern used by habit_logs.user_id.
    workout_session_id uuid        NOT NULL REFERENCES public.workout_sessions(id) ON DELETE CASCADE,
    content            text        NOT NULL,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.workout_notes
    IS 'Free-text notes per workout session. Cascade-deleted with the parent session.';

COMMENT ON COLUMN public.workout_notes.user_id
    IS 'Denormalised from workout_sessions for efficient RLS checks without a join.';

CREATE TRIGGER workout_notes_updated_at
    BEFORE UPDATE ON public.workout_notes
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



-- All session queries are scoped to a single user.
CREATE INDEX idx_workout_sessions_user_id
    ON public.workout_sessions(user_id);

-- Calendar / history view: "my workouts in this date range", newest first.
-- Composite covers both the equality filter and the ORDER BY in one scan.
CREATE INDEX idx_workout_sessions_user_started_at
    ON public.workout_sessions(user_id, started_at DESC);

-- Effort-level filter: "show only hard and max sessions".
CREATE INDEX idx_workout_sessions_user_effort
    ON public.workout_sessions(user_id, effort_level)
    WHERE effort_level IS NOT NULL;

-- Character module processing: "all unprocessed sessions for a user".
-- Partial index: rows leave this index the moment they are marked processed,
-- keeping it compact and fast regardless of total session count.
CREATE INDEX idx_workout_sessions_pending
    ON public.workout_sessions(user_id)
    WHERE is_processed = false;

-- ── workout_goals ─────────────────────────────────────────────

CREATE INDEX idx_workout_goals_user_id
    ON public.workout_goals(user_id);

-- ── workout_notes ─────────────────────────────────────────────

-- Notes are almost always fetched by their parent session.
CREATE INDEX idx_workout_notes_session_id
    ON public.workout_notes(workout_session_id);

-- User-scoped note queries (e.g. "all my notes").
CREATE INDEX idx_workout_notes_user_id
    ON public.workout_notes(user_id);


CREATE OR REPLACE FUNCTION public.calculate_effort_level(
    p_avg_heart_rate numeric
)
RETURNS public.workout_effort_level
LANGUAGE plpgsql
IMMUTABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    IF    p_avg_heart_rate IS NULL  THEN RETURN NULL;
    ELSIF p_avg_heart_rate <  100   THEN RETURN 'light';
    ELSIF p_avg_heart_rate <  130   THEN RETURN 'moderate';
    ELSIF p_avg_heart_rate <  160   THEN RETURN 'hard';
    ELSE                                 RETURN 'max';
    END IF;
END;
$$;

COMMENT ON FUNCTION public.calculate_effort_level(numeric) IS
    'Maps avg_heart_rate (bpm) to workout_effort_level. '
    'Returns NULL for sessions with no heart rate data. '
    'Zones: <100=light, 100–129=moderate, 130–159=hard, ≥160=max.';



-- ── workout_sessions ──────────────────────────────────────────

ALTER TABLE public.workout_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "workout_sessions: owner full access"
    ON public.workout_sessions
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── workout_goals ─────────────────────────────────────────────

ALTER TABLE public.workout_goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "workout_goals: owner full access"
    ON public.workout_goals
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── workout_notes ─────────────────────────────────────────────

ALTER TABLE public.workout_notes ENABLE ROW LEVEL SECURITY;

-- workout_notes carries its own user_id column so the policy can
-- filter on a local column without a join to workout_sessions.
-- Access to notes in other users' sessions is already impossible
-- because the FK requires a matching workout_sessions row, and
-- workout_sessions is itself RLS-protected.
CREATE POLICY "workout_notes: owner full access"
    ON public.workout_notes
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);
