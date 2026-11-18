from fastapi import APIRouter, Depends, HTTPException
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from tally_common.db import get_session
from tally_common.security import CurrentUser, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
password_hasher = PasswordHash.recommended()


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(credentials: LoginRequest, session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.email == credentials.email))

    if user is None or not password_hasher.verify(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.user_id, user.email, user.role.value)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user), session: Session = Depends(get_session)):
    # The token is verified by get_current_user; also confirm the account still exists.
    db_user = session.get(User, user.user_id)
    if db_user is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    return {"user_id": db_user.user_id, "email": db_user.email, "role": db_user.role.value}
