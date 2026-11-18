"""JSON endpoints over the analytics views.

This service's database login (analytics_reader) can read only the analytics.* views,
never the base tables. Tableau connects to the same views directly with that login, so
anything Tableau needs should be a view in db/ddl.sql, not a query in this file.

Available views: order_line_facts, revenue_by_month, top_products, low_stock,
unpaid_invoices, stock_movement_facts, daily_stock_levels, order_status_changes,
order_cycle_times.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from tally_common.db import get_session
from tally_common.security import require_roles

router = APIRouter(
    prefix="/reports",
    tags=["reports"],
    dependencies=[Depends(require_roles("admin", "sales"))],
)


def rows(session: Session, sql: str) -> list[dict]:
    return [dict(row) for row in session.execute(text(sql)).mappings()]


@router.get("/revenue-by-month")
def revenue_by_month(session: Session = Depends(get_session)):
    return rows(session, "SELECT * FROM analytics.revenue_by_month ORDER BY month")


@router.get("/low-stock")
def low_stock(session: Session = Depends(get_session)):
    return rows(session, "SELECT * FROM analytics.low_stock ORDER BY shortfall DESC, sku")


# TODO(analytics): endpoints for the other views, and the Tableau workbook (see README).
