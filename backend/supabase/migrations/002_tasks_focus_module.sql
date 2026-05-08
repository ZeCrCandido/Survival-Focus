
CREATE TYPE public.task_priority AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE public.task_status AS ENUM (
    'pending',
    'in_progress',
    'completed',
    'cancelled'
);

-- Used on tasks to define which focus mode the user prefers for it.
CREATE TYPE public.task_focus_type AS ENUM (
    'pomodoro',
    'stopwatch',
    'none'
);

-- Used on focus_sessions to record what mode was actually used.
CREATE TYPE public.session_type AS ENUM (
    'pomodoro',
    'stopwatch'
);



CREATE TABLE public.categories (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        text        NOT NULL,
    -- Stored as a CSS hex color string; validated by regex.
    color       text        NOT NULL CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    -- Icon identifier (e.g. an icon name from an icon library used by the frontend).
    icon        text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    -- A user cannot have two categories with the same name.
    UNIQUE (user_id, name)
);

COMMENT ON TABLE  public.categories       IS 'User-defined categories for organising tasks (e.g. Work, Health, Study).';
COMMENT ON COLUMN public.categories.color IS 'CSS hex color, e.g. #FF5733. Validated by check constraint.';
COMMENT ON COLUMN public.categories.icon  IS 'Icon key from the frontend icon library (e.g. "briefcase", "heart").';



CREATE TABLE public.tags (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name        text        NOT NULL,
    color       text        NOT NULL CHECK (color ~ '^#[0-9A-Fa-f]{6}$'),
    created_at  timestamptz NOT NULL DEFAULT now(),
    -- A user cannot have two tags with the same name.
    UNIQUE (user_id, name)
);

COMMENT ON TABLE public.tags IS 'User-defined labels for quick cross-category filtering (e.g. "urgent", "personal").';



CREATE TABLE public.tasks (
    id                         uuid             PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                    uuid             NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    -- Nullable: tasks can exist without a category.
    category_id                uuid             REFERENCES public.categories(id) ON DELETE SET NULL,
    title                      text             NOT NULL,
    description                text,
    priority                   public.task_priority    NOT NULL DEFAULT 'medium',
    status                     public.task_status      NOT NULL DEFAULT 'pending',
    -- Preferred focus mode for this task; 'none' means the user times freely.
    focus_type                 public.task_focus_type  NOT NULL DEFAULT 'none',
    due_date                   timestamptz,
    -- Set automatically by trigger when status transitions to 'completed'.
    completed_at               timestamptz,
    -- 1–100 integer predicting how much completing this task will boost the
    -- character's next exploration event. Calculated by the app and stored here
    -- so it can be displayed on the task card without a live recalculation.
    estimated_adventure_impact integer          CHECK (estimated_adventure_impact BETWEEN 1 AND 100),
    created_at                 timestamptz      NOT NULL DEFAULT now(),
    updated_at                 timestamptz      NOT NULL DEFAULT now(),
    -- Enforce that completed_at is only set when the task is actually completed.
    CONSTRAINT completed_at_matches_status CHECK (
        (status = 'completed' AND completed_at IS NOT NULL) OR
        (status != 'completed' AND completed_at IS NULL)
    )
);

COMMENT ON TABLE  public.tasks                            IS 'Core task entity. Status and focus data feed both productivity tracking and survival game mechanics.';
COMMENT ON COLUMN public.tasks.estimated_adventure_impact IS 'App-calculated score (1-100) predicting the effect on the next character exploration event.';
COMMENT ON COLUMN public.tasks.completed_at              IS 'Populated automatically by trigger on status → completed; cleared if reverted.';



CREATE TABLE public.task_tags (
    task_id     uuid NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    tag_id      uuid NOT NULL REFERENCES public.tags(id)  ON DELETE CASCADE,
    PRIMARY KEY (task_id, tag_id)
);

COMMENT ON TABLE public.task_tags IS 'Many-to-many junction between tasks and tags.';



CREATE TABLE public.focus_sessions (
    id               uuid              PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          uuid              NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    task_id          uuid              NOT NULL REFERENCES public.tasks(id) ON DELETE CASCADE,
    type             public.session_type NOT NULL,
    started_at       timestamptz       NOT NULL DEFAULT now(),
    -- Null while the session is still active.
    ended_at         timestamptz,
    -- Populated on session end: EXTRACT(EPOCH FROM (ended_at - started_at)).
    duration_seconds integer           CHECK (duration_seconds >= 0),
    -- false if the user abandoned the session before completion.
    was_completed    boolean           NOT NULL DEFAULT false,
    -- Survival resources the character earned during this session.
    -- See migration notes for the chosen JSONB schema.
    resources_earned jsonb,
    created_at       timestamptz       NOT NULL DEFAULT now(),
    -- Temporal integrity: ended_at must be after started_at when present.
    CONSTRAINT valid_session_window CHECK (
        ended_at IS NULL OR ended_at > started_at
    ),
    -- duration_seconds is only meaningful after the session ends.
    CONSTRAINT duration_requires_end CHECK (
        duration_seconds IS NULL OR ended_at IS NOT NULL
    )
);

COMMENT ON TABLE  public.focus_sessions                  IS 'Records each individual Pomodoro or Stopwatch session linked to a task.';
COMMENT ON COLUMN public.focus_sessions.resources_earned IS 'JSONB: { xp, resources: { food, water, medicine, ammo, scrap, fuel }, bonus: { type, label, multiplier } | null }';
COMMENT ON COLUMN public.focus_sessions.was_completed    IS 'false when the user ends a session early; used to gate partial resource rewards.';

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER categories_updated_at
    BEFORE UPDATE ON public.categories
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER tasks_updated_at
    BEFORE UPDATE ON public.tasks
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Auto-manage completed_at when task status changes.
-- Removing the need for the API to always send completed_at explicitly.
CREATE OR REPLACE FUNCTION public.sync_task_completed_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    -- Transition INTO completed → stamp the time.
    IF NEW.status = 'completed' AND (OLD.status IS DISTINCT FROM 'completed') THEN
        NEW.completed_at = now();
    END IF;
    -- Transition OUT OF completed → clear the stamp.
    IF NEW.status != 'completed' AND OLD.status = 'completed' THEN
        NEW.completed_at = NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER task_sync_completed_at
    BEFORE UPDATE ON public.tasks
    FOR EACH ROW EXECUTE FUNCTION public.sync_task_completed_at();


CREATE INDEX idx_categories_user_id
    ON public.categories(user_id);

-- ── tags ─────────────────────────────────────────────────────
CREATE INDEX idx_tags_user_id
    ON public.tags(user_id);

-- ── tasks ────────────────────────────────────────────────────
-- Dashboard: "all my tasks" — most common query, needs user_id alone.
CREATE INDEX idx_tasks_user_id
    ON public.tasks(user_id);

-- Dashboard filtering: "show pending tasks" — status alone for aggregate reports.
CREATE INDEX idx_tasks_status
    ON public.tasks(status);

-- Partial index: due_date is often NULL; index only the rows where it matters.
CREATE INDEX idx_tasks_due_date
    ON public.tasks(due_date)
    WHERE due_date IS NOT NULL;

-- Partial index: category_id is nullable; skip uncategorised tasks.
CREATE INDEX idx_tasks_category_id
    ON public.tasks(category_id)
    WHERE category_id IS NOT NULL;

-- Composite: "my pending tasks ordered by due date" — covers the primary
-- task list query in one index scan.
CREATE INDEX idx_tasks_user_status
    ON public.tasks(user_id, status);

-- Composite: upcoming tasks for a given user, NULL-excluded.
CREATE INDEX idx_tasks_user_due_date
    ON public.tasks(user_id, due_date)
    WHERE due_date IS NOT NULL;

-- ── task_tags ────────────────────────────────────────────────
-- task_id is already part of the composite PK (left-most column),
-- so a PK index already covers lookups by task_id.
-- Add a standalone index on tag_id for reverse lookups: "all tasks with tag X".
CREATE INDEX idx_task_tags_tag_id
    ON public.task_tags(tag_id);

-- ── focus_sessions ────────────────────────────────────────────
CREATE INDEX idx_focus_sessions_user_id
    ON public.focus_sessions(user_id);

CREATE INDEX idx_focus_sessions_task_id
    ON public.focus_sessions(task_id);

-- Useful for analytics: "all completed sessions for a user" (productivity history).
CREATE INDEX idx_focus_sessions_user_completed
    ON public.focus_sessions(user_id, was_completed);


-- ============================================================
-- 9. ROW LEVEL SECURITY
-- ============================================================

-- ── categories ───────────────────────────────────────────────
ALTER TABLE public.categories ENABLE ROW LEVEL SECURITY;

-- Single all-operations policy: USING filters SELECT/UPDATE/DELETE;
-- WITH CHECK gates INSERT/UPDATE writes.
CREATE POLICY "categories: owner full access"
    ON public.categories
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── tags ─────────────────────────────────────────────────────
ALTER TABLE public.tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tags: owner full access"
    ON public.tags
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── tasks ────────────────────────────────────────────────────
ALTER TABLE public.tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tasks: owner full access"
    ON public.tasks
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);


-- ── task_tags ────────────────────────────────────────────────
-- No user_id column — access is derived from task ownership.
-- The EXISTS subquery leverages idx_tasks_user_id and the tasks PK.
ALTER TABLE public.task_tags ENABLE ROW LEVEL SECURITY;

CREATE POLICY "task_tags: access via task ownership"
    ON public.task_tags
    USING (
        EXISTS (
            SELECT 1
            FROM   public.tasks
            WHERE  tasks.id      = task_tags.task_id
              AND  tasks.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1
            FROM   public.tasks
            WHERE  tasks.id      = task_tags.task_id
              AND  tasks.user_id = auth.uid()
        )
    );


-- ── focus_sessions ────────────────────────────────────────────
ALTER TABLE public.focus_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "focus_sessions: owner full access"
    ON public.focus_sessions
    USING     (auth.uid() = user_id)
    WITH CHECK(auth.uid() = user_id);
