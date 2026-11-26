from datetime import datetime, timedelta, timezone
from hmac import compare_digest, digest

import jwt
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import add_user, password_hasher
from app.models import User, UserRole
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from tally_common.config import get_settings
from tally_common.db import get_session
from tally_common.security import CurrentUser, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_AUDIENCE = "tally-auth-refresh"
REFRESH_LIFETIME = timedelta(days=7)


def _password_binding(secret: str, password_hash: str) -> str:
    """Bind refresh tokens to the current password hash without exposing it."""
    return digest(secret.encode(), f"refresh:{password_hash}".encode(), "sha256").hex()


@router.post("/login", response_model=LoginResponse)
def login(credentials: LoginRequest, response: Response, session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.email == credentials.email))

    if user is None or not password_hasher.verify(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    settings = get_settings()
    refresh_token = jwt.encode(
        {
            "sub": str(user.user_id),
            "aud": REFRESH_AUDIENCE,
            "exp": datetime.now(timezone.utc) + REFRESH_LIFETIME,
            "pwd": _password_binding(settings.jwt_secret, user.password_hash),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    response.headers["Cache-Control"] = "no-store"
    return LoginResponse(
        access_token=create_access_token(user.user_id, user.email, user.role.value),
        refresh_token=refresh_token,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, response: Response, session: Session = Depends(get_session)):
    """Exchange a valid refresh token for a new access token."""
    settings = get_settings()
    unauthorized = HTTPException(status_code=401, detail="Invalid or expired refresh token")
    try:
        claims = jwt.decode(
            data.refresh_token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=REFRESH_AUDIENCE,
            options={"require": ["sub", "aud", "exp", "pwd"]},
        )
        user_id = int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError):
        raise unauthorized from None

    user = session.get(User, user_id)
    binding = claims["pwd"]
    if user is None or not isinstance(binding, str) or not binding.isascii():
        raise unauthorized
    if not compare_digest(binding, _password_binding(settings.jwt_secret, user.password_hash)):
        raise unauthorized

    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=create_access_token(user.user_id, user.email, user.role.value))


@router.post("/register", status_code=201, response_model=UserResponse)
def register(data: RegisterRequest, session: Session = Depends(get_session)):
    """Create a customer login. Customer profiles belong to the transactions service."""
    return add_user(session, data.email, data.password, UserRole.customer)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)):
    # The token is verified by get_current_user; also confirm the account still exists.
    db_user = session.get(User, user.user_id)
    if db_user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return {"user_id": db_user.user_id, "email": db_user.email, "role": db_user.role.value}


@router.patch("/password", response_model=MessageResponse)
def change_password(
    data: ChangePasswordRequest,
    user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Change the caller's password after verifying their current password."""
    # Serialize password changes so simultaneous requests must verify the latest hash.
    account = session.scalar(select(User).where(User.user_id == user.user_id).with_for_update())
    if account is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    if not password_hasher.verify(data.current_password, account.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    account.password_hash = password_hasher.hash(data.new_password)
    session.commit()
    return {"message": "Password updated"}
