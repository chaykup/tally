from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import add_user, password_hasher
from app.models import User, UserRole
from app.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from tally_common.db import get_session
from tally_common.security import CurrentUser, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])
@router.post("/login", response_model=TokenResponse)
def login(credentials: LoginRequest, session: Session = Depends(get_session)):
    user = session.scalar(select(User).where(User.email == credentials.email))

    if user is None or not password_hasher.verify(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user.user_id, user.email, user.role.value)
    return {"access_token": token, "token_type": "bearer"}


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
