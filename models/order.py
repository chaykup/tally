from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    FetchedValue,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class OrderStatus(str, Enum):
    pending = "pending"
    confirmed = "confirmed"
    cancelled = "cancelled"
    invoiced = "invoiced"


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        Index("idx_orders_customer", "customer_id"),
        Index("idx_orders_created_by", "created_by"),
        Index("idx_orders_status_date", "status", "order_date"),
        Index("idx_orders_date", "order_date"),
    )

    order_id: Mapped[int] = mapped_column(
        Integer, Identity(always=False), primary_key=True
    )

    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("customers.customer_id", name="fk_orders_customers"),
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.user_id", name="fk_orders_created_by"),
        nullable=False,
    )

    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    delivery_address: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    status: Mapped[OrderStatus] = mapped_column(
        PGEnum(OrderStatus, name="order_status", create_type=False),
        nullable=False,
        server_default=text("'pending'"),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )

    lines: Mapped[list["OrderLine"]] = relationship(
        "OrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
