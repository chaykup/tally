"""Order pipeline and invoice reports (analytics.order_cycle_times, order_status_changes, unpaid_invoices)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import STAFF_ONLY, DateRange, OrderStatus, Page, date_range, fetch_all, page, where
from app.schemas import OrderCycleTime, OrderStatusChange, PipelineStatus, UnpaidInvoice
from tally_common.db import get_session

router = APIRouter(prefix="/reports", tags=["order reports"], dependencies=STAFF_ONLY)

ORDER_DAY = "(order_date AT TIME ZONE 'UTC')::date"


@router.get("/order-pipeline", response_model=list[PipelineStatus])
def order_pipeline(dates: DateRange = Depends(date_range), session: Session = Depends(get_session)):
    """Orders per current status, with average and median hours to confirm and invoice.

    The date range filters by order date. Statuses with no orders are left out.
    """
    filters = where(
        f"{ORDER_DAY} >= :start" if dates.start else None,
        f"{ORDER_DAY} <= :end" if dates.end else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT
            current_status AS status,
            count(*)       AS order_count,
            round(avg(hours_to_confirm), 2) AS avg_hours_to_confirm,
            round((percentile_cont(0.5) WITHIN GROUP (ORDER BY hours_to_confirm))::numeric, 2)
                           AS median_hours_to_confirm,
            round(avg(hours_to_invoice), 2) AS avg_hours_to_invoice
        FROM analytics.order_cycle_times
        {filters}
        GROUP BY current_status
        ORDER BY array_position(ARRAY['pending', 'confirmed', 'invoiced', 'cancelled'], current_status)
        """,
        start=dates.start,
        end=dates.end,
    )


@router.get("/order-cycle-times", response_model=list[OrderCycleTime])
def order_cycle_times(
    dates: DateRange = Depends(date_range),
    status: OrderStatus | None = None,
    paging: Page = Depends(page),
    session: Session = Depends(get_session),
):
    """One row per order with when it reached each status, newest orders first."""
    filters = where(
        f"{ORDER_DAY} >= :start" if dates.start else None,
        f"{ORDER_DAY} <= :end" if dates.end else None,
        "current_status = :status" if status else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT * FROM analytics.order_cycle_times
        {filters}
        ORDER BY order_date DESC, order_id DESC
        LIMIT :limit OFFSET :offset
        """,
        start=dates.start,
        end=dates.end,
        status=status,
        limit=paging.limit,
        offset=paging.offset,
    )


@router.get("/order-status-changes", response_model=list[OrderStatusChange])
def order_status_changes(
    dates: DateRange = Depends(date_range),
    order_id: int | None = None,
    paging: Page = Depends(page),
    session: Session = Depends(get_session),
):
    """Every order status change, newest first. Pass order_id for one order's timeline."""
    filters = where(
        "changed_day_utc >= :start" if dates.start else None,
        "changed_day_utc <= :end" if dates.end else None,
        "order_id = :order_id" if order_id is not None else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT * FROM analytics.order_status_changes
        {filters}
        ORDER BY changed_at DESC, history_id DESC
        LIMIT :limit OFFSET :offset
        """,
        start=dates.start,
        end=dates.end,
        order_id=order_id,
        limit=paging.limit,
        offset=paging.offset,
    )


@router.get("/unpaid-invoices", response_model=list[UnpaidInvoice])
def unpaid_invoices(
    overdue_only: bool = False,
    customer_id: int | None = None,
    session: Session = Depends(get_session),
):
    """Unpaid invoices, most overdue first."""
    filters = where(
        "is_overdue" if overdue_only else None,
        "customer_id = :customer_id" if customer_id is not None else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT * FROM analytics.unpaid_invoices
        {filters}
        ORDER BY days_overdue DESC, due_date, invoice_number
        """,
        customer_id=customer_id,
    )
