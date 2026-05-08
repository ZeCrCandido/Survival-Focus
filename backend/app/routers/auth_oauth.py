from fastapi import APIRouter, Request
from app.core.supabase_client import get_supabase
from starlette.responses import RedirectResponse

router = APIRouter()


@router.get('/auth/oauth/google')
async def oauth_google(request: Request):
    # Build the Supabase OAuth URL and redirect the browser
    client = get_supabase()
    # supabase-py create_client does not expose a get_authorization_url helper
    # so return a simple redirect to the typical Supabase OAuth endpoint
    base = client.url
    # Compose redirect to Supabase's hosted auth (the project URL)
    url = f"{base}/auth/v1/authorize?provider=google"
    return RedirectResponse(url)
