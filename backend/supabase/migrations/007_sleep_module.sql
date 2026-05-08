
CREATE TYPE sleep_quality_enum AS ENUM ('poor', 'fair', 'good', 'excellent');

CREATE TYPE sleep_goal_type_enum AS ENUM (
    'total_sleep_hours',
    'deep_sleep_hours',
    'rem_sleep_hours',
    'sleep_consistency'
);


CREATE TABLE public.sleep_sessions (
    id                  uuid            PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid            NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- The calendar date this sleep night belongs to (parsed from the JSON "date" field).
    external_date       date            NOT NULL,

    -- Origin of the data; defaults to apple_health for this import flow.
    source              text            NOT NULL DEFAULT 'apple_health',

    -- Raw timestamps from the JSON, stored with timezone context.
    sleep_start         timestamptz     NOT NULL,
    sleep_end           timestamptz     NOT NULL,
    in_bed_start        timestamptz     NOT NULL,
    in_bed_end          timestamptz     NOT NULL,

    -- Total sleep duration in both units.
    total_sleep_hours   numeric(5, 3)   NOT NULL,
    total_sleep_minutes integer         NOT NULL,

    -- REM sleep duration in both units.
    rem_hours           numeric(5, 3)   NOT NULL DEFAULT 0,
    rem_minutes         integer         NOT NULL DEFAULT 0,

    -- Deep (slow-wave) sleep duration in both units.
    deep_hours          numeric(5, 3)   NOT NULL DEFAULT 0,
    deep_minutes        integer         NOT NULL DEFAULT 0,

    -- Core / light sleep duration in both units.
    core_hours          numeric(5, 3)   NOT NULL DEFAULT 0,
    core_minutes        integer         NOT NULL DEFAULT 0,

    -- Time awake during the night in both units.
    awake_hours         numeric(5, 3)   NOT NULL DEFAULT 0,
    awake_minutes       integer         NOT NULL DEFAULT 0,

    -- Derived quality label; computed at import time via calculate_sleep_quality().
    sleep_quality       sleep_quality_enum NOT NULL DEFAULT 'fair',

    -- Nullable JSONB blob that carries derived effects on the game character
    -- (e.g. stamina bonus, mood penalty). Populated by application logic.
    character_impact    jsonb,

    -- Processing pipeline flags.
    is_processed        boolean         NOT NULL DEFAULT false,
    processed_at        timestamptz,

    -- Full original JSON entry kept for auditing / re-parsing.
    raw_data            jsonb,

    created_at          timestamptz     NOT NULL DEFAULT now(),
    updated_at          timestamptz     NOT NULL DEFAULT now(),

    -- One sleep record per calendar night per user.
    CONSTRAINT uq_sleep_sessions_user_date UNIQUE (user_id, external_date),

    -- Sanity checks: end must be after start, durations must be non-negative.
    CONSTRAINT chk_sleep_end_after_start   CHECK (sleep_end > sleep_start),
    CONSTRAINT chk_in_bed_end_after_start  CHECK (in_bed_end > in_bed_start),
    CONSTRAINT chk_total_sleep_hours_pos   CHECK (total_sleep_hours >= 0),
    CONSTRAINT chk_rem_hours_pos           CHECK (rem_hours >= 0),
    CONSTRAINT chk_deep_hours_pos          CHECK (deep_hours >= 0),
    CONSTRAINT chk_core_hours_pos          CHECK (core_hours >= 0),
    CONSTRAINT chk_awake_hours_pos         CHECK (awake_hours >= 0)
);

-- Auto-update updated_at on every row modification.
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_sleep_sessions_updated_at
    BEFORE UPDATE ON public.sleep_sessions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


CREATE TABLE public.sleep_goals (
    id              uuid                    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid                    NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    goal_type       sleep_goal_type_enum    NOT NULL,

    -- Stored as numeric to accommodate both hour-based targets (e.g. 7.5 hrs)
    -- and percentage/streak targets for sleep_consistency (e.g. 80 = 80 %).
    target_value    numeric                 NOT NULL,

    created_at      timestamptz             NOT NULL DEFAULT now(),
    updated_at      timestamptz             NOT NULL DEFAULT now(),

    CONSTRAINT uq_sleep_goals_user_type UNIQUE (user_id, goal_type),
    CONSTRAINT chk_target_value_pos     CHECK (target_value > 0)
);

CREATE TRIGGER trg_sleep_goals_updated_at
    BEFORE UPDATE ON public.sleep_goals
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



CREATE TABLE public.sleep_notes (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    sleep_session_id    uuid        NOT NULL REFERENCES public.sleep_sessions(id) ON DELETE CASCADE,

    content             text        NOT NULL,

    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_note_content_not_empty CHECK (trim(content) <> '')
);

CREATE TRIGGER trg_sleep_notes_updated_at
    BEFORE UPDATE ON public.sleep_notes
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



CREATE OR REPLACE FUNCTION public.calculate_sleep_quality(
    p_total_sleep_hours numeric,
    p_deep_hours        numeric,
    p_rem_hours         numeric
)
RETURNS sleep_quality_enum
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_base_score  integer := 0;
    v_deep_score  integer := 0;
    v_rem_score   integer := 0;
    v_total_score integer;
    v_deep_ratio  numeric;
    v_rem_ratio   numeric;
BEGIN
    -- Guard: treat zero or negative total sleep as the worst possible input.
    IF p_total_sleep_hours IS NULL OR p_total_sleep_hours <= 0 THEN
        RETURN 'poor';
    END IF;

    -- Base score — total sleep duration.
    v_base_score := CASE
        WHEN p_total_sleep_hours < 5.0                                  THEN 0
        WHEN p_total_sleep_hours >= 5.0 AND p_total_sleep_hours < 6.0   THEN 1
        WHEN p_total_sleep_hours >= 6.0 AND p_total_sleep_hours < 7.0   THEN 2
        WHEN p_total_sleep_hours >= 7.0 AND p_total_sleep_hours < 9.0   THEN 3
        ELSE 2  -- >= 9.0 h (oversleeping)
    END;

    -- Deep sleep ratio score.
    v_deep_ratio := COALESCE(p_deep_hours, 0) / p_total_sleep_hours;
    v_deep_score := CASE
        WHEN v_deep_ratio < 0.10  THEN 0
        WHEN v_deep_ratio < 0.20  THEN 1
        ELSE 2
    END;

    -- REM sleep ratio score.
    v_rem_ratio := COALESCE(p_rem_hours, 0) / p_total_sleep_hours;
    v_rem_score := CASE
        WHEN v_rem_ratio < 0.15  THEN 0
        WHEN v_rem_ratio < 0.25  THEN 1
        ELSE 2
    END;

    v_total_score := v_base_score + v_deep_score + v_rem_score;

    RETURN CASE
        WHEN v_total_score <= 2 THEN 'poor'
        WHEN v_total_score <= 4 THEN 'fair'
        WHEN v_total_score <= 6 THEN 'good'
        ELSE 'excellent'
    END;
END;
$$;



-- sleep_sessions
CREATE INDEX idx_sleep_sessions_user_id       ON public.sleep_sessions (user_id);
CREATE INDEX idx_sleep_sessions_external_date ON public.sleep_sessions (user_id, external_date DESC);
CREATE INDEX idx_sleep_sessions_quality       ON public.sleep_sessions (user_id, sleep_quality);
CREATE INDEX idx_sleep_sessions_is_processed  ON public.sleep_sessions (is_processed) WHERE is_processed = false;

-- sleep_goals
CREATE INDEX idx_sleep_goals_user_id          ON public.sleep_goals (user_id);

-- sleep_notes
CREATE INDEX idx_sleep_notes_session_id       ON public.sleep_notes (sleep_session_id);
CREATE INDEX idx_sleep_notes_user_id          ON public.sleep_notes (user_id);


-- sleep_sessions
ALTER TABLE public.sleep_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sleep_sessions: users select own rows"
    ON public.sleep_sessions FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "sleep_sessions: users insert own rows"
    ON public.sleep_sessions FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "sleep_sessions: users update own rows"
    ON public.sleep_sessions FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "sleep_sessions: users delete own rows"
    ON public.sleep_sessions FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());


-- sleep_goals
ALTER TABLE public.sleep_goals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sleep_goals: users select own rows"
    ON public.sleep_goals FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "sleep_goals: users insert own rows"
    ON public.sleep_goals FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "sleep_goals: users update own rows"
    ON public.sleep_goals FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "sleep_goals: users delete own rows"
    ON public.sleep_goals FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());


-- sleep_notes
ALTER TABLE public.sleep_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "sleep_notes: users select own rows"
    ON public.sleep_notes FOR SELECT
    TO authenticated
    USING (user_id = auth.uid());

CREATE POLICY "sleep_notes: users insert own rows"
    ON public.sleep_notes FOR INSERT
    TO authenticated
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "sleep_notes: users update own rows"
    ON public.sleep_notes FOR UPDATE
    TO authenticated
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "sleep_notes: users delete own rows"
    ON public.sleep_notes FOR DELETE
    TO authenticated
    USING (user_id = auth.uid());