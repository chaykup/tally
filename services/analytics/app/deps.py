"""Shared query helpers and request parameters for the report routers."""

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from tally_common.security import require_roles

# Every report is for staff. Customers get 403 and anonymous callers 401.
STAFF_ONLY = [Depends(require_roles("admin", "sales"))]

OrderStatus = Literal["pending", "confirmed", "cancelled", "invoiced"]
MovementReason = Literal["initial", "receipt", "sale", "sale_cancelled", "adjustment", "transfer"]


def fetch_all(session: Session, sql: str, **params) -> list[dict]:
    """Run a read-only query and return plain dicts. Always bind values through params."""
    return [dict(row) for row in session.execute(text(sql), params).mappings()]


def fetch_one(session: Session, sql: str, **params) -> dict:
    return dict(session.execute(text(sql), params).mappings().one())


def where(*conditions: str | None) -> str:
    """Join the non-empty SQL conditions into a WHERE clause.

    Conditions must be fixed strings written in code (with :named params for values),
    never text built from user input.
    """
    parts = [c for c in conditions if c]
    return f"WHERE {' AND '.join(parts)}" if parts else ""


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


@dataclass(frozen=True)
class DateRange:
    start: date | None
    end: date | None


def date_range(
    start: date | None = Query(None, description="First UTC day to include (YYYY-MM-DD)."),
    end: date | None = Query(None, description="Last UTC day to include (YYYY-MM-DD)."),
) -> DateRange:
    """Optional inclusive date range, shared by most reports."""
    if start and end and start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    return DateRange(start, end)


@dataclass(frozen=True)
class Page:
    limit: int
    offset: int


def page(
    limit: int = Query(100, ge=1, le=1000, description="Maximum rows to return."),
    offset: int = Query(0, ge=0, description="Rows to skip, for paging."),
) -> Page:
    return Page(limit, offset)
