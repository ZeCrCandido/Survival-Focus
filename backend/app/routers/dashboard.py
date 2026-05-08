from fastapi import APIRouter

from app.dependencies.auth import CurrentUser
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard import get_dashboard

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
async def dashboard(user: CurrentUser) -> DashboardResponse:
    """
    Returns the complete aggregated app state in a single request.
    All sub-queries execute concurrently — target latency equals the
    slowest single query, not their sum.
    """
    return await get_dashboard(user.user_id)
