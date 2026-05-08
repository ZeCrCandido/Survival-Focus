
-- ── 1. New columns ───────────────────────────────────────────

ALTER TABLE public.habit_logs
    ADD COLUMN IF NOT EXISTS is_processed boolean     NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS processed_at timestamptz;

COMMENT ON COLUMN public.habit_logs.is_processed IS
    'False until the character module has consumed this log''s character_impact. '
    'Set to true by POST /habit-impact/process alongside processed_at.';

COMMENT ON COLUMN public.habit_logs.processed_at IS
    'UTC timestamp of when the character module processed this log. NULL while pending.';


-- ── 2. Indexes ───────────────────────────────────────────────

-- Partial index: the "pending" query filters to (user_id, is_processed=false).
-- A partial index on is_processed=false keeps it small — once rows are marked
-- processed they leave this index automatically.
CREATE INDEX IF NOT EXISTS idx_habit_logs_pending_user
    ON public.habit_logs(user_id)
    WHERE is_processed = false;

-- Composite index: the "history" query filters by (user_id, is_processed=true)
-- and sorts by processed_at DESC.
CREATE INDEX IF NOT EXISTS idx_habit_logs_history_user
    ON public.habit_logs(user_id, processed_at DESC)
    WHERE is_processed = true;
