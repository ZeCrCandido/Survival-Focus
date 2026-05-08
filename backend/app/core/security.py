from dataclasses import dataclass

import httpx
from jose import ExpiredSignatureError, JWTError, jwt
from jose.exceptions import JWTClaimsError

from app.core.config import settings

# Supabase sets `aud` to "authenticated" for every logged-in user token.
# Anon tokens carry "anon" — we reject those here.
_AUDIENCE = "authenticated"

_SUPPORTED_ALGORITHMS = ["HS256", "RS256", "ES256"]

_cached_jwks: dict[str, object] | None = None


def _get_supabase_jwks() -> dict[str, object]:
    global _cached_jwks

    if _cached_jwks is not None:
        return _cached_jwks

    jwks_url = f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    response = httpx.get(jwks_url, timeout=5.0)
    response.raise_for_status()
    jwks = response.json()

    if not isinstance(jwks, dict) or "keys" not in jwks:
        raise ValueError("Invalid JWKS payload from Supabase")

    _cached_jwks = jwks
    return jwks


@dataclass(frozen=True)
class TokenPayload:
    user_id: str   # `sub` claim — Supabase user UUID
    email: str     # `email` claim injected by Supabase Auth


def decode_supabase_jwt(token: str) -> TokenPayload:
    """
    Validate a Supabase-issued JWT and return its core claims.

    Raises:
        ValueError: with a human-readable reason on any validation failure.
            Callers should map this to HTTP 401.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise ValueError(f"Invalid token header: {exc}")

    alg = header.get("alg")
    if alg not in _SUPPORTED_ALGORITHMS:
        raise ValueError(f"Unsupported JWT algorithm: {alg}")

    key = settings.supabase_jwt_secret if alg == "HS256" else _get_supabase_jwks()

    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            audience=_AUDIENCE,
            issuer=f"{settings.supabase_url.rstrip('/')}/auth/v1",
        )
    except ExpiredSignatureError:
        raise ValueError("Token has expired.")
    except JWTClaimsError as exc:
        # Covers wrong audience, issuer mismatch, etc.
        raise ValueError(f"Invalid token claims: {exc}")
    except JWTError as exc:
        raise ValueError(f"Token validation failed: {exc}")

    user_id: str | None = payload.get("sub")
    email: str | None = payload.get("email")

    if not user_id:
        raise ValueError("Token is missing the 'sub' claim.")
    if not email:
        raise ValueError("Token is missing the 'email' claim.")

    return TokenPayload(user_id=user_id, email=email)
