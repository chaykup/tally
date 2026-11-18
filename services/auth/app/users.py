from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User
from tally_common.db import get_session
from tally_common.security import require_roles

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", dependencies=[Depends(require_roles("admin"))])
def list_users(session: Session = Depends(get_session)):
    users = session.scalars(select(User).order_by(User.user_id))
    return [{"user_id": u.user_id, "email": u.email, "role": u.role.value} for u in users]
