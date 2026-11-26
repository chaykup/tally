"""ORM models for the sales schema, which this service owns.

db/ddl.sql is the source of truth for the schema. These models only map onto it:
never call Base.metadata.create_all(). Change ddl.sql first, then update the model.

The Order / OrderLine models started on the feat/orders branch belong in this file (or
an app/models/ package). When moving them over:
  * add  __table_args__ = {"schema": "sales"}  (or a tuple ending in that dict)
  * point foreign keys at schema-qualified names: "sales.customers.customer_id",
    "accounts.users.user_id", "inventory.products.item_id", "inventory.stock.item_id", ...
  * the order_status enum lives in the sales schema: PGEnum(..., schema="sales", create_type=False)

Placing or cancelling an order changes inventory.stock.quantity. Call
tally_common.audit.set_change_context(session, movement_reason="sale", order_id=..., user_id=...)
in the same transaction first, or the database rejects the stock change.
"""
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    func,
)

from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from datetime import datetime


class Base(DeclarativeBase):
    pass

# External tables used by foreign keys.
# These belong to other services, not Transactions.

Table(
    "users",
    Base.metadata,
    Column("user_id", Integer, primary_key=True),
    schema="accounts",
)

Table(
    "products",
    Base.metadata,
    Column("item_id", Integer, primary_key=True),
    schema="inventory",
)

Table(
    "warehouses",
    Base.metadata,
    Column("warehouse_id", Integer, primary_key=True),
    schema="inventory",
)

Table(
    "stock",
    Base.metadata,
    Column("inventory_id", Integer, primary_key=True),
    Column("item_id", Integer),
    Column("warehouse_id", Integer),
    UniqueConstraint(
        "item_id",
        "warehouse_id",
        name="uq_stock_item_warehouse",
    ),
    schema="inventory",
)



class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "sales"}

    customer_id: Mapped[int] = mapped_column(primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    user_id: Mapped[int | None]  # the customer's own login (accounts.users), if any
    sales_rep_id: Mapped[int]    # the sales user who owns this account
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set by a database trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )

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
        {"schema": "sales"},
    )

    order_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=False),
        primary_key=True,
    )

    customer_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "sales.customers.customer_id",
            name="fk_orders_customers",
        ),
        nullable=False,
    )

    created_by: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "accounts.users.user_id",
            name="fk_orders_created_by",
        ),
        nullable=False,
    )

    order_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    delivery_address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[OrderStatus] = mapped_column(
        PGEnum(
            OrderStatus,
            name="order_status",
            schema="sales",
            create_type=False,
        ),
        nullable=False,
        server_default="pending",
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
            [
                "inventory.stock.item_id",
                "inventory.stock.warehouse_id",
            ],
            name="fk_lines_stock",
        ),
        Index(
            "idx_lines_item_warehouse",
            "item_id",
            "warehouse_id",
        ),
        {"schema": "sales"},
    )

    line_id: Mapped[int] = mapped_column(
        Integer,
        Identity(always=False),
        primary_key=True,
    )

    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "sales.orders.order_id",
            name="fk_lines_order",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    item_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "inventory.products.item_id",
            name="fk_lines_product",
        ),
        nullable=False,
    )

    warehouse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(
            "inventory.warehouses.warehouse_id",
            name="fk_lines_warehouse",
        ),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    order: Mapped["Order"] = relationship(
        "Order",
        back_populates="lines",
    )
