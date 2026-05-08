from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import TokenPayload, decode_supabase_jwt

# HTTPBearer extracts the token from the `Authorization: Bearer <token>` header.
# auto_error=False lets us return a custom 401 instead of FastAPI's default 403.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> TokenPayload:
    """
    FastAPI dependency — validates the Bearer token and returns the caller's
    identity.  Inject with `user: CurrentUser` on any protected route.

    Raises HTTP 401 when:
      - The Authorization header is absent or malformed.
      - The JWT signature is invalid.
      - The token has expired.
      - Required claims (sub, email) are missing.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        return decode_supabase_jwt(credentials.credentials)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )


# Convenience alias — use `user: CurrentUser` in route signatures.
CurrentUser = Annotated[TokenPayload, Depends(get_current_user)]
