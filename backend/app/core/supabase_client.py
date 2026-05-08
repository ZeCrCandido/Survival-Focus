from supabase import Client, create_client

from app.core.config import settings

# Service-role client — bypasses RLS entirely.
# All user-level access control is enforced upstream via the JWT auth dependency.
# Never expose the service role key to clients.
_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
    return _client
