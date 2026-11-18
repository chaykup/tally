from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from tally_common.db import get_session
from tally_common.security import CurrentUser, get_current_user

router = APIRouter(prefix="/products", tags=["products"])


# Example endpoint showing the pattern: auth dependency, session dependency, ORM query.
@router.get("")
def list_products(
    _user: CurrentUser = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    products = session.scalars(select(Product).where(Product.is_active).order_by(Product.item_id))
    return [
        {"item_id": p.item_id, "sku": p.sku, "item_name": p.item_name, "unit_price": str(p.unit_price)}
        for p in products
    ]


# TODO(inventory): create/update products, warehouses, stock receipts and adjustments.
