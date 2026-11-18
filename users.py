from fastapi import APIRouter, Depends

from auth import require_admin
from db import connect

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", dependencies=[Depends(require_admin)])
def list_users():
    with connect() as conn:
        rows = conn.execute(
            "SELECT user_id, email, role FROM users ORDER BY user_id"
        ).fetchall()

    return [
        {"user_id": user_id, "email": email, "role": role}
        for user_id, email, role in rows
    ]