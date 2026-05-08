from .categories import router as categories
from .character import router as character
from .dashboard import router as dashboard
from .exploration import router as exploration
from .focus import router as focus
from .habits import router as habits
from .habit_impact import router as habit_impact
from .inventory import router as inventory
from .profile import router as profile
from .sleep import router as sleep
from .tags import router as tags
from .tasks import router as tasks
from .workouts import router as workouts
from .auth_oauth import router as auth_oauth

# This package exposes each router object as a module-level name so callers
# can import e.g. `from app.routers import habits as habits_router` and
# then use `habits_router.router` when including into the main FastAPI app.

