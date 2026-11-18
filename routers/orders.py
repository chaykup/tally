from fastapi import APIRouter, Depends
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from schemas.order import OrderResponse
from models.order import Order
from database import get_db

router = APIRouter(prefix="/orders", tags=["Orders"])



# TO BE ADDED:
# DEPENDENCIES = [Depends(require_customer)]
@router.post("")
def create_order(order: Order):
    pass





@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)

    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    return order