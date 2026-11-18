from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer
from tally_common.db import get_session
from tally_common.security import CurrentUser, require_roles

router = APIRouter(prefix="/customers", tags=["customers"])


# Example endpoint showing the pattern: role check, then scope the query to the caller.
@router.get("")
def list_customers(
    user: CurrentUser = Depends(require_roles("admin", "sales")),
    session: Session = Depends(get_session),
):
    query = select(Customer).order_by(Customer.customer_id)
    if user.role == "sales":
        query = query.where(Customer.sales_rep_id == user.user_id)  # reps see only their accounts
    return [
        {"customer_id": c.customer_id, "customer_name": c.customer_name, "email": c.email}
        for c in session.scalars(query)
    ]


# TODO(transactions): orders (place, confirm, cancel), order lines, invoices.
