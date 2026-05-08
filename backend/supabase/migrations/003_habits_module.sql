
-- Whether a habit builds the character up or tears it down.
CREATE TYPE public.habit_nature AS ENUM (
    'healthy',   -- exercising, drinking water, meditating — character gains
    'harmful'    -- smoking, junk food, screen time — character takes damage
);

-- How frequently the habit should be performed to count towards a streak.
CREATE TYPE public.habit_frequency AS ENUM (
    'daily',   -- must be logged every day
    'weekly'   -- must be logged at least once per week
);



CREATE TABLE public.habits (
    id           uuid                   PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid                   NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name         text                   NOT NULL,
    description  text,
    nature       public.habit_nature    NOT NULL,
    -- How often the habit must be performed to maintain a streak.
    frequency    public.habit_frequency NOT NULL DEFAULT 'daily',
    -- Optional numeric target (e.g. 8 for "8 glasses of water").
    target_value integer,
    -- Unit label rendered next to target_value in the UI (e.g. "glasses", "km").
    unit         text,
    color        text                   NOT NULL CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    -- Icon identifier from the frontend icon library (e.g. "dumbbell", "droplet").
    icon         text,
    -- Soft-delete: inactive habits are hidden from the dashboard but preserved
    -- in habit_logs so historical data and streaks remain intact.
    is_active    boolean                NOT NULL DEFAULT true,
    created_at   timestamptz            NOT NULL DEFAULT now(),
    updated_at   timestamptz            NOT NULL DEFAULT now(),
    -- Prevent a user from creating two habits with the same name.
    UNIQUE (user_id, name)
);

COMMENT ON TABLE  public.habits              IS 'Habit definitions. Each user creates habits that are tracked daily or weekly.';
COMMENT ON COLUMN public.habits.nature       IS 'healthy = character gains; harmful = character takes damage on completion.';
COMMENT ON COLUMN public.habits.target_value IS 'Numeric goal, e.g. 8. Paired with unit for display: "8 glasses".';
COMMENT ON COLUMN public.habits.is_active    IS 'False hides the habit from the dashboard; logs are preserved for historical data.';

-- Reuse the set_updated_at() function defined in migration 001.
CREATE TRIGGER habits_updated_at
    BEFORE UPDATE ON public.habits
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();




CREATE TABLE public.habit_logs (
    id               uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- user_id is stored directly for efficient RLS checks and user-scoped queries
    -- without requiring a join to the habits table on every read.
    user_id          uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    habit_id         uuid        NOT NULL REFERENCES public.habits(id) ON DELETE CASCADE,
    -- The calendar day this log refers to (not the timestamp of entry).
    -- Stored as date, not timestamptz, so one entry per day is unambiguous
    -- regardless of the user's timezone — the frontend sends the local date.
    logged_at        date        NOT NULL DEFAULT CURRENT_DATE,
    -- Actual value performed (e.g. 6 glasses if target was 8).
    -- NULL is valid for binary habits (done/not done).
    value            integer,
    -- True if the target_value was met (or for binary habits, if it was done).
    was_completed    boolean     NOT NULL DEFAULT false,
    notes            text,
    -- Calculated effect on character stats for this specific log entry.
    -- Populated by the FastAPI service layer after persisting the log.
    -- See migration notes for the JSONB schema.
    character_impact jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),
    -- One log entry per habit per day — prevents duplicate logging.
    CONSTRAINT habit_logs_unique_day UNIQUE (habit_id, logged_at)
);

COMMENT ON TABLE  public.habit_logs                  IS 'Daily performance records for each habit. One row per habit per calendar day.';
COMMENT ON COLUMN public.habit_logs.logged_at        IS 'Local calendar date sent by the client — stored as date, not timestamp.';
COMMENT ON COLUMN public.habit_logs.value            IS 'Actual quantity performed. NULL for binary (done/not-done) habits.';
COMMENT ON COLUMN public.habit_logs.character_impact IS 'JSONB: { type, health_delta, skill_xp: {skill→points}, survival_score_delta, morale_delta }. Set by the service layer.';




CREATE TABLE public.habit_skills (
    id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    habit_id              uuid        NOT NULL REFERENCES public.habits(id) ON DELETE CASCADE,
    -- Free-form string so new skills can be introduced without schema changes.
    -- Examples: "strength", "endurance", "focus", "agility", "immunity".
    skill_name            text        NOT NULL,
    -- XP awarded to skill_name for each successful log (was_completed = true).
    points_per_completion integer     NOT NULL CHECK (points_per_completion > 0),
    created_at            timestamptz NOT NULL DEFAULT now(),
    -- A habit cannot contribute to the same skill twice.
    UNIQUE (habit_id, skill_name)
);

COMMENT ON TABLE  public.habit_skills                       IS 'Maps healthy habits to character skills. Completed logs award points_per_completion XP to the skill.';
COMMENT ON COLUMN public.habit_skills.skill_name            IS 'Character skill key, e.g. "strength". Free-form for extensibility.';
COMMENT ON COLUMN public.habit_skills.points_per_completion IS 'XP credited to skill_name every time the parent habit is logged as completed.';




-- Most habit queries are scoped to a single user.
CREATE INDEX idx_habits_user_id
    ON public.habits(user_id);

-- Dashboard: "show my active habits" — composite covers both filters in one scan.
CREATE INDEX idx_habits_user_active
    ON public.habits(user_id, is_active);

-- Partial index for global "active habit" queries (e.g. scheduled reminders).
CREATE INDEX idx_habits_is_active
    ON public.habits(is_active)
    WHERE is_active = true;

-- ── habit_logs ───────────────────────────────────────────────

-- Streak and calendar queries pivot on habit_id.
CREATE INDEX idx_habit_logs_habit_id
    ON public.habit_logs(habit_id);

-- User-scoped log queries (e.g. "what did I log today?").
CREATE INDEX idx_habit_logs_user_id
    ON public.habit_logs(user_id);

-- Date-range queries (weekly/monthly dashboard views).
CREATE INDEX idx_habit_logs_logged_at
    ON public.habit_logs(logged_at);

-- Composite: streak function scans (habit_id, logged_at DESC) frequently.
CREATE INDEX idx_habit_logs_habit_date
    ON public.habit_logs(habit_id, logged_at DESC);

-- Composite: "all of my logs for a given date range" — primary dashboard query.
CREATE INDEX idx_habit_logs_user_date
    ON public.habit_logs(user_id, logged_at DESC);

-- ── habit_skills ─────────────────────────────────────────────

-- Skill lookups always start from a habit_id.
CREATE INDEX idx_habit_skills_habit_id
    ON public.habit_skills(habit_id);




CREATE OR REPLACE FUNCTION public.calculate_habit_streak(p_habit_id uuid)
RETURNS integer
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_streak    integer                := 0;
    v_prev_date date                   := NULL;
    v_frequency public.habit_frequency;
    v_max_gap   integer;
    v_log       record;
BEGIN
    -- ── 1. Fetch the habit's frequency ────────────────────────
    SELECT frequency
    INTO   v_frequency
    FROM   public.habits
    WHERE  id = p_habit_id;

    IF NOT FOUND THEN
        RETURN 0;   -- habit does not exist
    END IF;

    -- ── 2. Determine the allowed gap between consecutive logs ──
    -- daily  → each completion must be at most 1 day apart
    -- weekly → each completion must be at most 7 days apart
    -- The gap is also used to decide whether the streak is still "live":
    -- if the most recent completion is older than v_max_gap days, the
    -- streak has already expired.
    v_max_gap := CASE v_frequency
        WHEN 'daily'  THEN 1
        WHEN 'weekly' THEN 7
        ELSE 1
    END;

    -- ── 3. Walk completed logs newest → oldest ────────────────
    FOR v_log IN
        SELECT logged_at
        FROM   public.habit_logs
        WHERE  habit_id      = p_habit_id
          AND  was_completed = true
        ORDER  BY logged_at DESC
    LOOP
        IF v_prev_date IS NULL THEN
            -- First (most recent) completed log.
            -- Guard: if it is older than v_max_gap days the streak is
            -- already broken — no need to examine earlier entries.
            IF v_log.logged_at >= (CURRENT_DATE - v_max_gap) THEN
                v_streak    := 1;
                v_prev_date := v_log.logged_at;
            ELSE
                RETURN 0;   -- last completion too old; streak expired
            END IF;

        ELSE
            -- Subsequent logs: check that the gap to the previous date
            -- does not exceed v_max_gap (streak is consecutive).
            IF (v_prev_date - v_log.logged_at) <= v_max_gap THEN
                v_streak    := v_streak + 1;
                v_prev_date := v_log.logged_at;
            ELSE
                -- Gap too large — the streak broke here; stop counting.
                EXIT;
            END IF;
        END IF;
    END LOOP;

    RETURN v_streak;
END;
$$;

COMMENT ON FUNCTION public.calculate_habit_streak(uuid) IS
    'Returns the current consecutive streak (periods) for a habit based on completed habit_logs. '
    'Returns 0 if the most recent completion is older than the frequency window (1 day for daily, 7 days for weekly).';


-- ============================================================
-- 7. ROW LEVEL SECURITY
-- ============================================================

-- ── habits ───────────────────────────────────────────────────
ALTER TABLE public.habits ENABLE ROW LEVEL SECURITY;

-- Single all-operations policy (USING → SELECT/UPDATE/DELETE,
-- WITH CHECK → INSERT/UPDATE writes).
CREATE POLICY "habits: owner full access"
    ON public.habits
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── habit_logs ───────────────────────────────────────────────
ALTER TABLE public.habit_logs ENABLE ROW LEVEL SECURITY;

-- user_id column is present directly, same pattern as tasks/categories.
CREATE POLICY "habit_logs: owner full access"
    ON public.habit_logs
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── habit_skills ─────────────────────────────────────────────
-- No user_id column — ownership is derived from the parent habit.
-- The EXISTS subquery uses idx_habits_user_id + habits PK for efficiency
-- (same pattern as task_tags in migration 002).
ALTER TABLE public.habit_skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY "habit_skills: access via habit ownership"
    ON public.habit_skills
    USING (
        EXISTS (
            SELECT 1
            FROM   public.habits
            WHERE  habits.id      = habit_skills.habit_id
              AND  habits.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM   public.habits
            WHERE  habits.id      = habit_skills.habit_id
              AND  habits.user_id = auth.uid()
        )
    );
