"""ORM models for the inventory schema, which this service owns.

db/ddl.sql is the source of truth for the schema. These models only map onto it:
never call Base.metadata.create_all(). Change ddl.sql first, then update the model.

Changing stock.quantity? Call tally_common.audit.set_change_context(...) first so the
automatic stock_movements row records the reason (receipt, adjustment, transfer, ...).
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, FetchedValue, ForeignKey, Numeric, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "inventory"}

    item_id: Mapped[int] = mapped_column(primary_key=True)
    item_name: Mapped[str] = mapped_column(String(100))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    description: Mapped[str | None] = mapped_column(String(500))
    sku: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set by a database trigger on every UPDATE.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )


class Warehouse(Base):
    __tablename__ = "warehouses"
    __table_args__ = {"schema": "inventory"}

    warehouse_id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_name: Mapped[str] = mapped_column(String(50))
    location_code: Mapped[str] = mapped_column(String(50))


class Stock(Base):
    __tablename__ = "stock"
    __table_args__ = {"schema": "inventory"}

    inventory_id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("inventory.products.item_id"))
    warehouse_id: Mapped[int] = mapped_column(ForeignKey("inventory.warehouses.warehouse_id"))
    quantity: Mapped[int] = mapped_column(server_default="0")
    reorder_threshold: Mapped[int] = mapped_column(server_default="0")
    # Set by a database trigger on every UPDATE.
    last_update_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), server_onupdate=FetchedValue()
    )

    product: Mapped[Product] = relationship()
    warehouse: Mapped[Warehouse] = relationship()
