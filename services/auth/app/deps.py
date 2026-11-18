"""Account creation shared by registration and the admin user router."""

from fastapi import Depends, HTTPException
from pwdlib import PasswordHash
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import User, UserRole
from app.schemas import UserResponse
from tally_common.security import require_roles

ADMIN_ONLY = [Depends(require_roles("admin"))]
password_hasher = PasswordHash.recommended()


def add_user(session: Session, email: str, password: str, role: UserRole) -> UserResponse:
    """Create an account, letting the unique constraint resolve duplicate requests."""
    user = session.scalar(
        insert(User)
        .values(email=email, password_hash=password_hasher.hash(password), role=role)
        .on_conflict_do_nothing(constraint="uq_users_email")
        .returning(User)
    )
    if user is None:
        session.rollback()
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    response = UserResponse.model_validate(user)
    session.commit()
    return response
