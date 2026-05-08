
CREATE TABLE IF NOT EXISTS public.level_up_events (
    id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    character_id    uuid        NOT NULL
                                REFERENCES public.characters(id)
                                ON DELETE CASCADE,
    old_level       integer     NOT NULL CHECK (old_level >= 1),
    new_level       integer     NOT NULL CHECK (new_level > old_level),
    levelled_up_at  timestamptz NOT NULL DEFAULT now()
);


CREATE INDEX IF NOT EXISTS idx_level_up_events_character_timeline
    ON public.level_up_events (character_id, levelled_up_at DESC);

-- ── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE public.level_up_events ENABLE ROW LEVEL SECURITY;


CREATE POLICY "level_up_events_read_own"
    ON public.level_up_events
    FOR SELECT
    USING (
        character_id IN (
            SELECT id FROM public.characters WHERE user_id = auth.uid()
        )
    );


DROP FUNCTION IF EXISTS public.calculate_level_up(uuid);

CREATE FUNCTION public.calculate_level_up(p_character_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_old_level  integer;
    v_new_level  integer;
    v_banked_xp  bigint;
    v_threshold  bigint;
BEGIN
    -- Lock the row so concurrent reward-processing calls don't race.
    SELECT level, experience_points
    INTO   v_old_level, v_banked_xp
    FROM   public.characters
    WHERE  id = p_character_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Character % not found', p_character_id;
    END IF;

    v_new_level := v_old_level;

    -- Drain XP across as many levels as the banked total allows.
    LOOP
        v_threshold := v_new_level * 100;
        EXIT WHEN v_banked_xp < v_threshold;
        v_banked_xp := v_banked_xp - v_threshold;
        v_new_level := v_new_level + 1;
    END LOOP;

    -- Persist only when something actually changed.
    IF v_new_level > v_old_level THEN
        UPDATE public.characters
        SET    level             = v_new_level,
               experience_points = v_banked_xp,
               updated_at        = now()
        WHERE  id = p_character_id;

        INSERT INTO public.level_up_events
               (character_id, old_level, new_level)
        VALUES (p_character_id, v_old_level, v_new_level);
    END IF;

    RETURN v_new_level;
END;
$$;

COMMENT ON FUNCTION public.calculate_level_up(uuid) IS
    'Drains banked XP against the N×100 threshold ladder, levels the character
     up as many times as the XP allows, and records every level-up in
     level_up_events.  Called by the FastAPI reward-processing engine after
     every pending_rewards flush.';
