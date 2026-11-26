from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from app.models import OrderStatus


# Individual item submitted during checkout
class OrderLineCreate(BaseModel):
    item_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    quantity: int = Field(gt=0)


# Request body for creating an order
class OrderCreate(BaseModel):
    customer_id: int = Field(gt=0)
    delivery_address: str = Field(
        min_length=1,
        max_length=255,
    )
    items: list[OrderLineCreate] = Field(min_length=1)


# Individual order line returned from the database
class OrderLineResponse(BaseModel):
    line_id: int
    item_id: int
    warehouse_id: int
    quantity: int
    unit_price: Decimal

    model_config = ConfigDict(from_attributes=True)


# Complete order returned to the client
class OrderResponse(BaseModel):
    order_id: int
    customer_id: int
    created_by: int
    order_date: datetime
    delivery_address: str
    status: OrderStatus
    updated_at: datetime
    lines: list[OrderLineResponse]

    model_config = ConfigDict(from_attributes=True)

class OrderStatusUpdate(BaseModel):
    status: Literal["confirmed"]