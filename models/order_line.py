from __future__ import annotations

from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.base import Base


class OrderLine(Base):
    __tablename__ = "order_lines"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "item_id",
            "warehouse_id",
            name="uq_lines_order_item_wh",
        ),
        CheckConstraint(
            "quantity > 0",
            name="chk_lines_quantity",
        ),
        CheckConstraint(
            "unit_price >= 0",
            name="chk_lines_price",
        ),
        ForeignKeyConstraint(
            ["item_id", "warehouse_id"],
            ["stock.item_id", "stock.warehouse_id"],
            name="fk_lines_stock",
        ),
        Index(
            "idx_lines_item_warehouse",
            "item_id",
            "warehouse_id",
        ),
    )

    line_id: Mapped[int] = mapped_column(
        Integer, Identity(always=False), primary_key=True
    )

    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "orders.order_id",
            name="fk_lines_order",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("products.item_id", name="fk_lines_product"),
        nullable=False,
    )

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("warehouses.warehouse_id", name="fk_lines_warehouse"),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer, nullable=False
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False
    )

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="lines",
    )
