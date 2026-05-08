from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.dependencies.auth import CurrentUser
from app.routers import categories as categories_router
from app.routers import character as character_router
from app.routers import dashboard as dashboard_router
from app.routers import exploration as exploration_router
from app.routers import inventory as inventory_router
from app.routers import focus as focus_router
from app.routers import habit_impact as habit_impact_router
from app.routers import habits as habits_router
from app.routers import workouts as workouts_router
from app.routers import sleep as sleep_router
from app.routers import profile as profile_router
from app.routers import tags as tags_router
from app.routers import tasks as tasks_router

app = FastAPI(
    title="Survival Focus API",
    version="0.1.0",
    description="Backend for Survival Focus — a post-apocalyptic productivity game.",
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Versioned API routers ────────────────────────────────────
app.include_router(dashboard_router,    prefix="/api/v1")
app.include_router(profile_router,      prefix="/api/v1")
app.include_router(categories_router,   prefix="/api/v1")
app.include_router(tags_router,         prefix="/api/v1")
app.include_router(tasks_router,        prefix="/api/v1")
app.include_router(focus_router,        prefix="/api/v1")
app.include_router(habits_router,       prefix="/api/v1")
app.include_router(habit_impact_router, prefix="/api/v1")
app.include_router(workouts_router,     prefix="/api/v1")
app.include_router(sleep_router,        prefix="/api/v1")
app.include_router(character_router,    prefix="/api/v1")
app.include_router(inventory_router,    prefix="/api/v1")
app.include_router(exploration_router,  prefix="/api/v1")


# ── Public routes ────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok", "env": settings.app_env}


# ── Auth smoke-test route ─────────────────────────────────────

@app.get("/me", tags=["auth"])
def get_me(user: CurrentUser):
    """Confirms JWT validation is working end-to-end."""
    return {"user_id": user.user_id, "email": user.email}
