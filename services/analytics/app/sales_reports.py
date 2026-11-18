"""Revenue and product sales reports (analytics.revenue_by_month, analytics.order_line_facts)."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.deps import STAFF_ONLY, DateRange, OrderStatus, Page, date_range, fetch_all, fetch_one, page, where
from app.schemas import MonthlyRevenue, OrderLineFact, ProductSales, Summary
from tally_common.db import get_session

router = APIRouter(prefix="/reports", tags=["sales reports"], dependencies=STAFF_ONLY)


@router.get("/summary", response_model=Summary)
def summary(session: Session = Depends(get_session)):
    """Headline numbers for the top of a dashboard. Months are UTC calendar months.

    Revenue and orders_this_month count only confirmed and invoiced orders.
    """
    return fetch_one(
        session,
        """
        WITH cur AS (SELECT date_trunc('month', now() AT TIME ZONE 'UTC')::date AS m)
        SELECT
            now() AS as_of,
            COALESCE((SELECT r.revenue FROM analytics.revenue_by_month r, cur WHERE r.month = cur.m), 0.00)
                AS revenue_this_month,
            COALESCE((SELECT r.revenue FROM analytics.revenue_by_month r, cur
                       WHERE r.month = (cur.m - interval '1 month')::date), 0.00)
                AS revenue_last_month,
            COALESCE((SELECT r.order_count FROM analytics.revenue_by_month r, cur WHERE r.month = cur.m), 0)
                AS orders_this_month,
            (SELECT count(*) FROM analytics.order_cycle_times WHERE current_status = 'pending')
                AS pending_orders,
            (SELECT count(*) FROM analytics.unpaid_invoices)                         AS unpaid_invoice_count,
            (SELECT COALESCE(sum(amount), 0.00) FROM analytics.unpaid_invoices)      AS unpaid_invoice_total,
            (SELECT count(*) FROM analytics.unpaid_invoices WHERE is_overdue)        AS overdue_invoice_count,
            (SELECT COALESCE(sum(amount), 0.00) FROM analytics.unpaid_invoices WHERE is_overdue)
                AS overdue_invoice_total,
            (SELECT count(*) FROM analytics.low_stock)                               AS low_stock_count
        """,
    )


@router.get("/revenue-by-month", response_model=list[MonthlyRevenue])
def revenue_by_month(dates: DateRange = Depends(date_range), session: Session = Depends(get_session)):
    """One row per month, oldest first, with zeros for months without sales (ready to chart).

    Defaults to the first month with revenue through the current month.
    """
    return fetch_all(
        session,
        """
        WITH bounds AS (
            SELECT
                date_trunc('month', COALESCE(
                    CAST(:start AS date),
                    (SELECT min(month) FROM analytics.revenue_by_month),
                    (now() AT TIME ZONE 'UTC')::date))::date AS first_month,
                date_trunc('month', COALESCE(
                    CAST(:end AS date),
                    (now() AT TIME ZONE 'UTC')::date))::date AS last_month
        )
        SELECT
            m::date                      AS month,
            COALESCE(r.order_count, 0)   AS order_count,
            COALESCE(r.units_sold, 0)    AS units_sold,
            COALESCE(r.revenue, 0.00)    AS revenue
        FROM bounds
        CROSS JOIN generate_series(bounds.first_month, bounds.last_month, interval '1 month') AS m
        LEFT JOIN analytics.revenue_by_month r ON r.month = m::date
        ORDER BY month
        """,
        start=dates.start,
        end=dates.end,
    )


TOP_PRODUCT_ORDER = {"revenue": "revenue", "units": "units_sold"}


@router.get("/top-products", response_model=list[ProductSales])
def top_products(
    dates: DateRange = Depends(date_range),
    sort_by: Literal["revenue", "units"] = "revenue",
    limit: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_session),
):
    """Best sellers by revenue or units, optionally within a date range (by order date)."""
    order_by = TOP_PRODUCT_ORDER[sort_by]  # fixed column name, never user text
    filters = where(
        "counts_as_revenue",
        "order_day_utc >= :start" if dates.start else None,
        "order_day_utc <= :end" if dates.end else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT item_id, sku, item_name,
               count(DISTINCT order_id) AS order_count,
               sum(quantity)            AS units_sold,
               sum(line_total)          AS revenue
        FROM analytics.order_line_facts
        {filters}
        GROUP BY item_id, sku, item_name
        ORDER BY {order_by} DESC, sku
        LIMIT :limit
        """,
        start=dates.start,
        end=dates.end,
        limit=limit,
    )


@router.get("/order-lines", response_model=list[OrderLineFact])
def order_lines(
    dates: DateRange = Depends(date_range),
    status: OrderStatus | None = None,
    item_id: int | None = None,
    customer_id: int | None = None,
    paging: Page = Depends(page),
    session: Session = Depends(get_session),
):
    """Raw order line facts, newest first. Includes every status; filter with `status`."""
    filters = where(
        "order_day_utc >= :start" if dates.start else None,
        "order_day_utc <= :end" if dates.end else None,
        "order_status = :status" if status else None,
        "item_id = :item_id" if item_id is not None else None,
        "customer_id = :customer_id" if customer_id is not None else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT * FROM analytics.order_line_facts
        {filters}
        ORDER BY order_date DESC, order_id DESC, sku
        LIMIT :limit OFFSET :offset
        """,
        start=dates.start,
        end=dates.end,
        status=status,
        item_id=item_id,
        customer_id=customer_id,
        limit=paging.limit,
        offset=paging.offset,
    )
