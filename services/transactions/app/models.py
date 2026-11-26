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

from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


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
