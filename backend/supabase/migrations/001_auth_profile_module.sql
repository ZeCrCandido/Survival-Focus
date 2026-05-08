

CREATE TABLE public.avatar_types (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name         text        NOT NULL UNIQUE,          -- e.g. "The Medic", "The Scout"
    description  text        NOT NULL,
    image_url    text,                                 -- path/URL to character art asset
    traits       jsonb       NOT NULL DEFAULT '[]',    -- array of personality trait strings
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.avatar_types            IS 'Character archetypes a user can be assigned after completing onboarding.';
COMMENT ON COLUMN public.avatar_types.traits     IS 'Array of trait labels used for questionnaire scoring, e.g. ["resilient","analytical"].';
COMMENT ON COLUMN public.avatar_types.image_url  IS 'Relative path or CDN URL to the character illustration.';

-- Keep updated_at current automatically
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER avatar_types_updated_at
    BEFORE UPDATE ON public.avatar_types
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



CREATE TABLE public.onboarding_questions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    question_order smallint    NOT NULL UNIQUE,        -- display sequence, 1-based
    question_text  text        NOT NULL,
    -- Array of answer objects:
    -- [{ "label": "...", "trait_weights": { "resilient": 2, "analytical": 1 } }]
    answers        jsonb       NOT NULL DEFAULT '[]',
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.onboarding_questions         IS 'Personality questionnaire used during onboarding to assign an avatar archetype.';
COMMENT ON COLUMN public.onboarding_questions.answers IS 'JSON array of answer objects. Each has a "label" and "trait_weights" map matching avatar_types.traits.';

CREATE TRIGGER onboarding_questions_updated_at
    BEFORE UPDATE ON public.onboarding_questions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();


CREATE TABLE public.profiles (
    -- Mirror the auth.users primary key — no surrogate key needed.
    id                   uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    username             text UNIQUE,                  -- chosen during onboarding, nullable until set
    display_name         text,
    avatar_type_id       uuid REFERENCES public.avatar_types(id) ON DELETE SET NULL,
    onboarding_completed boolean     NOT NULL DEFAULT false,
    -- Survival-game identity extras (can grow with future modules)
    bio                  text,
    avatar_url           text,                         -- user-uploaded profile picture
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE  public.profiles                       IS 'User profile extending auth.users. Created automatically on signup.';
COMMENT ON COLUMN public.profiles.id                    IS 'Matches auth.users.id exactly — no separate surrogate key.';
COMMENT ON COLUMN public.profiles.onboarding_completed  IS 'Set to true once the user finishes the personality questionnaire.';
COMMENT ON COLUMN public.profiles.avatar_type_id        IS 'Assigned archetype derived from questionnaire scoring. NULL until onboarding is done.';

CREATE TRIGGER profiles_updated_at
    BEFORE UPDATE ON public.profiles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();



CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER                -- runs with elevated rights to write to public.profiles
SET search_path = public        -- prevent search-path hijacking
AS $$
BEGIN
    INSERT INTO public.profiles (id, display_name, avatar_url)
    VALUES (
        NEW.id,
        -- Prefer full_name from OAuth metadata; fall back to email prefix
        COALESCE(
            NEW.raw_user_meta_data->>'full_name',
            split_part(NEW.email, '@', 1)
        ),
        -- Google / GitHub OAuth providers put the picture here
        NEW.raw_user_meta_data->>'avatar_url'
    );
    RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();



-- ── 5a. profiles ────────────────────────────────────────────
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;

-- Users can read only their own profile
CREATE POLICY "profiles: owner can select"
    ON public.profiles FOR SELECT
    USING (auth.uid() = id);

-- Users can update only their own profile
CREATE POLICY "profiles: owner can update"
    ON public.profiles FOR UPDATE
    USING      (auth.uid() = id)
    WITH CHECK (auth.uid() = id);

-- INSERT is handled exclusively by the trigger (SECURITY DEFINER),
-- so no user-facing INSERT policy is needed.


-- ── 5b. avatar_types ────────────────────────────────────────
ALTER TABLE public.avatar_types ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read archetypes (needed during onboarding UI)
CREATE POLICY "avatar_types: authenticated users can select"
    ON public.avatar_types FOR SELECT
    TO authenticated
    USING (true);

-- Only service-role / migration scripts can INSERT / UPDATE / DELETE.
-- No additional policies → service_role bypasses RLS by default in Supabase.


-- ── 5c. onboarding_questions ────────────────────────────────
ALTER TABLE public.onboarding_questions ENABLE ROW LEVEL SECURITY;

-- All authenticated users can read questions
CREATE POLICY "onboarding_questions: authenticated users can select"
    ON public.onboarding_questions FOR SELECT
    TO authenticated
    USING (true);

-- Only service-role can mutate this reference data.



INSERT INTO public.avatar_types (name, description, image_url, traits) VALUES
(
    'The Medic',
    'Calm under pressure and driven by compassion. You keep the group alive through skill and sacrifice.',
    'assets/avatars/medic.png',
    '["compassionate","analytical","calm","resourceful"]'
),
(
    'The Scout',
    'Fast, perceptive, and always two steps ahead. You survive by reading the terrain before anyone else does.',
    'assets/avatars/scout.png',
    '["perceptive","agile","independent","adaptable"]'
),
(
    'The Enforcer',
    'Unyielding willpower and raw resilience. When the world ends, you make the hard calls others can''t.',
    'assets/avatars/enforcer.png',
    '["resilient","decisive","protective","bold"]'
),
(
    'The Strategist',
    'Survival is a puzzle you were born to solve. Every resource, every threat — already calculated.',
    'assets/avatars/strategist.png',
    '["analytical","strategic","patient","resourceful"]'
);



INSERT INTO public.onboarding_questions (question_order, question_text, answers) VALUES
(
    1,
    'The dead are closing in on your camp. What''s your first instinct?',
    '[
        {"label": "Patch up the wounded before we move",          "trait_weights": {"compassionate": 3, "calm": 2}},
        {"label": "Scout a safe route out immediately",           "trait_weights": {"perceptive": 3, "agile": 2}},
        {"label": "Stand your ground and fight them back",        "trait_weights": {"resilient": 3, "bold": 2}},
        {"label": "Map the threat perimeter before deciding",     "trait_weights": {"analytical": 3, "strategic": 2}}
    ]'
),
(
    2,
    'Supplies are running low. How do you contribute?',
    '[
        {"label": "Ration carefully and treat the sick first",    "trait_weights": {"compassionate": 2, "resourceful": 2}},
        {"label": "Go out and find more — I know where to look",  "trait_weights": {"independent": 2, "adaptable": 2}},
        {"label": "Protect what we have — no one steals from us", "trait_weights": {"protective": 3, "decisive": 1}},
        {"label": "Calculate exactly how long supplies will last", "trait_weights": {"analytical": 2, "patient": 2}}
    ]'
),
(
    3,
    'A stranger asks to join your group. What do you do?',
    '[
        {"label": "Check their wounds — they need help first",    "trait_weights": {"compassionate": 3, "calm": 1}},
        {"label": "Follow them discreetly before deciding",       "trait_weights": {"perceptive": 3, "independent": 1}},
        {"label": "Test their strength — earn your place",        "trait_weights": {"bold": 2, "resilient": 2}},
        {"label": "Interrogate them methodically for red flags",  "trait_weights": {"analytical": 2, "strategic": 2}}
    ]'
),
(
    4,
    'Your real-life productivity challenge is usually:',
    '[
        {"label": "I burn out helping others before helping myself", "trait_weights": {"compassionate": 2, "resourceful": 1}},
        {"label": "I start strong but lose focus mid-journey",       "trait_weights": {"adaptable": 2, "agile": 1}},
        {"label": "I procrastinate until the pressure forces me",    "trait_weights": {"resilient": 2, "decisive": 1}},
        {"label": "I over-plan and delay taking action",             "trait_weights": {"analytical": 2, "patient": 1}}
    ]'
),
(
    5,
    'What kind of survivor do you want to become?',
    '[
        {"label": "The one everyone turns to when it hurts",      "trait_weights": {"compassionate": 3, "calm": 2}},
        {"label": "The one who always finds a way through",       "trait_weights": {"adaptable": 2, "perceptive": 2}},
        {"label": "The one who never breaks, no matter what",     "trait_weights": {"resilient": 3, "bold": 1}},
        {"label": "The one whose plan saves everyone",            "trait_weights": {"strategic": 3, "patient": 1}}
    ]'
);
