"""ORM models for the accounts schema, which this service owns.

db/ddl.sql is the source of truth for the schema. These models only map onto it:
never call Base.metadata.create_all(). Change ddl.sql first, then update the model.
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserRole(str, Enum):
    admin = "admin"
    sales = "sales"
    customer = "customer"


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "accounts"}

    user_id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        PGEnum(UserRole, name="user_role", schema="accounts", create_type=False)
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
