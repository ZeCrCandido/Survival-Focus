from app.core.supabase_client import get_supabase
from app.models.profile import AvatarType, OnboardingQuestion, Profile
from app.schemas.profile import OnboardingAnswerSubmit, ProfileUpdateRequest


class ServiceError(Exception):
    """Raised by service functions to signal recoverable errors to the router."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _execute(query):
    """Execute a PostgREST query and surface any database-level errors cleanly."""
    try:
        return query.execute()
    except Exception as exc:
        raise ServiceError(f"Database error: {exc}", 500)


# ── Profile ───────────────────────────────────────────────────────────────────


def get_profile(user_id: str) -> Profile:
    response = _execute(
        get_supabase()
        .table("profiles")
        .select("*, avatar_types(*)")
        .eq("id", user_id)
    )
    if not response.data:
        raise ServiceError("Profile not found.", 404)
    return Profile.model_validate(response.data[0])


def update_profile(user_id: str, body: ProfileUpdateRequest) -> Profile:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise ServiceError("No updatable fields provided.", 400)

    response = _execute(
        get_supabase()
        .table("profiles")
        .update(updates)
        .eq("id", user_id)
        .select("*, avatar_types(*)")
    )
    if not response.data:
        raise ServiceError("Profile not found.", 404)
    return Profile.model_validate(response.data[0])


# ── Onboarding ────────────────────────────────────────────────────────────────


def get_onboarding_questions() -> list[OnboardingQuestion]:
    response = _execute(
        get_supabase()
        .table("onboarding_questions")
        .select("*")
        .order("question_order")
    )
    return [OnboardingQuestion.model_validate(row) for row in response.data]


def get_onboarding_status(user_id: str) -> tuple[bool, AvatarType | None]:
    response = _execute(
        get_supabase()
        .table("profiles")
        .select("onboarding_completed, avatar_types(*)")
        .eq("id", user_id)
    )
    if not response.data:
        raise ServiceError("Profile not found.", 404)

    row = response.data[0]
    completed: bool = row["onboarding_completed"]
    avatar_row = row.get("avatar_types")
    avatar = AvatarType.model_validate(avatar_row) if avatar_row else None
    return completed, avatar


def submit_onboarding(user_id: str, answers: list[OnboardingAnswerSubmit]) -> AvatarType:
    supabase = get_supabase()

    # ── Load reference data ───────────────────────────────────
    questions_resp = _execute(supabase.table("onboarding_questions").select("*"))
    questions_by_id: dict[str, dict] = {q["id"]: q for q in questions_resp.data}

    avatars_resp = _execute(supabase.table("avatar_types").select("*"))
    avatar_rows: list[dict] = avatars_resp.data

    if not avatar_rows:
        raise ServiceError("No avatar types are configured.", 500)

    # ── Validate all answers before scoring ───────────────────
    for answer in answers:
        qid = str(answer.question_id)
        question = questions_by_id.get(qid)
        if question is None:
            raise ServiceError(f"Question '{qid}' not found.", 400)
        if answer.answer_index >= len(question["answers"]):
            raise ServiceError(
                f"Answer index {answer.answer_index} is out of range "
                f"for question: \"{question['question_text']}\".",
                400,
            )

    # ── Score ─────────────────────────────────────────────────
    # For each selected answer, pull its trait_weights and accumulate a
    # running tally: { trait_name -> total_points }.
    trait_scores: dict[str, float] = {}
    for answer in answers:
        selected_option = questions_by_id[str(answer.question_id)]["answers"][
            answer.answer_index
        ]
        for trait, weight in selected_option.get("trait_weights", {}).items():
            trait_scores[trait] = trait_scores.get(trait, 0.0) + float(weight)

    # Each avatar type exposes a list of traits it embodies.
    # Its match score is the sum of the user's accumulated points for those traits.
    # Ties are broken alphabetically by avatar name for determinism.
    def avatar_score(av: dict) -> float:
        return sum(trait_scores.get(t, 0.0) for t in (av.get("traits") or []))

    best = max(avatar_rows, key=lambda av: (avatar_score(av), -ord(av["name"][0])))

    # ── Persist ───────────────────────────────────────────────
    _execute(
        supabase.table("profiles")
        .update({"avatar_type_id": best["id"], "onboarding_completed": True})
        .eq("id", user_id)
    )

    return AvatarType.model_validate(best)
