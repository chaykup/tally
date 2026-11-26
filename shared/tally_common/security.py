"""JWT access tokens. The auth service issues them; every service verifies them.

Tokens carry the user's id, email and role, so services can authorize requests without
reading accounts.users (most of them are not allowed to read password hashes anyway).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tally_common.config import get_settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    email: str
    role: str  # 'admin' | 'sales' | 'customer'


def create_access_token(user_id: int, email: str, role: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_minutes)
    claims = {"sub": str(user_id), "email": email, "role": role, "exp": expires_at}
    return jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Missing, invalid, or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> CurrentUser:
    """FastAPI dependency: the logged-in user, or 401."""
    if credentials is None:
        raise _unauthorized()
    settings = get_settings()
    try:
        claims = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["sub", "email", "role", "exp"]},
        )
        return CurrentUser(user_id=int(claims["sub"]), email=claims["email"], role=claims["role"])
    except (jwt.InvalidTokenError, ValueError):
        raise _unauthorized() from None


def require_roles(*roles: str):
    """FastAPI dependency factory: allow only these roles, e.g. Depends(require_roles("admin"))."""

    def check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(roles)}")
        return user

    return check
