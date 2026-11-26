from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.deps import ADMIN_ONLY, add_user
from app.models import User
from app.schemas import CreateUserRequest, UpdateRoleRequest, UserResponse
from tally_common.db import get_session

router = APIRouter(prefix="/users", tags=["users"], dependencies=ADMIN_ONLY)


@router.get("", response_model=list[UserResponse])
def list_users(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    users = session.scalars(select(User).order_by(User.user_id).limit(limit).offset(offset))
    return [{"user_id": u.user_id, "email": u.email, "role": u.role.value} for u in users]


@router.post("", status_code=201, response_model=UserResponse)
def create_user(data: CreateUserRequest, session: Session = Depends(get_session)):
    """Create an account with a role chosen by an admin."""
    return add_user(session, data.email, data.password, data.role)


@router.patch("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    data: UpdateRoleRequest,
    user_id: int = Path(gt=0),
    session: Session = Depends(get_session),
):
    """Change an account's role. Previously issued tokens retain their role until expiry."""
    user = session.scalar(
        update(User).where(User.user_id == user_id).values(role=data.role).returning(User)
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    response = UserResponse.model_validate(user)
    session.commit()
    return response
