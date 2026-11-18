import os
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from pwdlib import PasswordHash

from db import connect

router = APIRouter(prefix="/auth", tags=["auth"])
password_hasher = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(credentials: LoginRequest):
    with connect() as conn:
        user = conn.execute(
            "SELECT email, password_hash FROM users WHERE email = %s",
            (credentials.email,),
        ).fetchone()

    if user is None:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    email, password_hash = user
    if not password_hasher.verify(credentials.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    token = jwt.encode(
        {"sub": email, "exp": expires_at},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    return {"access_token": token, "token_type": "bearer"}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
):
    unauthorized = HTTPException(
        status_code=401,
        detail="Missing, invalid, or expired access token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise unauthorized

    try:
        claims = jwt.decode(
            credentials.credentials,
            os.environ["JWT_SECRET"],
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except jwt.InvalidTokenError:
        raise unauthorized from None

    with connect() as conn:
        user = conn.execute(
            "SELECT email, role FROM users WHERE email = %s",
            (claims["sub"],),
        ).fetchone()

    if user is None:
        raise unauthorized

    email, role = user
    return {"email": email, "role": role}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return user


def require_admin(user: dict = Depends(get_current_user)):
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")