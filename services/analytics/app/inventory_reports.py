"""Inventory reports (analytics.low_stock, daily_stock_levels, stock_movement_facts)."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import STAFF_ONLY, DateRange, MovementReason, Page, date_range, fetch_all, page, utc_today, where
from app.schemas import DailyStockLevel, LowStockItem, StockMovement
from tally_common.db import get_session

router = APIRouter(prefix="/reports", tags=["inventory reports"], dependencies=STAFF_ONLY)

DEFAULT_LEVEL_DAYS = 30
MAX_LEVEL_DAYS = 366


@router.get("/low-stock", response_model=list[LowStockItem])
def low_stock(warehouse_id: int | None = None, session: Session = Depends(get_session)):
    """Active products at or below their reorder threshold, largest shortfall first."""
    filters = where("warehouse_id = :warehouse_id" if warehouse_id is not None else None)
    return fetch_all(
        session,
        f"SELECT * FROM analytics.low_stock {filters} ORDER BY shortfall DESC, sku, warehouse_id",
        warehouse_id=warehouse_id,
    )


@router.get("/stock-levels", response_model=list[DailyStockLevel])
def stock_levels(
    dates: DateRange = Depends(date_range),
    item_id: int | None = None,
    warehouse_id: int | None = None,
    session: Session = Depends(get_session),
):
    """Closing stock per product, warehouse and day, for charting inventory over time.

    Defaults to the last 30 days, and allows at most 366. Days before a stock row's first
    movement are left out.
    """
    end = dates.end or utc_today()
    start = dates.start or end - timedelta(days=DEFAULT_LEVEL_DAYS - 1)
    if start > end:
        raise HTTPException(status_code=422, detail="start must be on or before end")
    if (end - start).days + 1 > MAX_LEVEL_DAYS:
        raise HTTPException(status_code=422, detail=f"date range is limited to {MAX_LEVEL_DAYS} days")

    filters = where(
        "day >= :start",
        "day <= :end",
        "item_id = :item_id" if item_id is not None else None,
        "warehouse_id = :warehouse_id" if warehouse_id is not None else None,
    )
    return fetch_all(
        session,
        f"SELECT * FROM analytics.daily_stock_levels {filters} ORDER BY sku, warehouse_id, day",
        start=start,
        end=end,
        item_id=item_id,
        warehouse_id=warehouse_id,
    )


@router.get("/stock-movements", response_model=list[StockMovement])
def stock_movements(
    dates: DateRange = Depends(date_range),
    item_id: int | None = None,
    warehouse_id: int | None = None,
    reason: MovementReason | None = None,
    paging: Page = Depends(page),
    session: Session = Depends(get_session),
):
    """Every stock change with the level after it, newest first."""
    filters = where(
        "movement_day_utc >= :start" if dates.start else None,
        "movement_day_utc <= :end" if dates.end else None,
        "item_id = :item_id" if item_id is not None else None,
        "warehouse_id = :warehouse_id" if warehouse_id is not None else None,
        "reason = :reason" if reason else None,
    )
    return fetch_all(
        session,
        f"""
        SELECT * FROM analytics.stock_movement_facts
        {filters}
        ORDER BY created_at DESC, movement_id DESC
        LIMIT :limit OFFSET :offset
        """,
        start=dates.start,
        end=dates.end,
        item_id=item_id,
        warehouse_id=warehouse_id,
        reason=reason,
        limit=paging.limit,
        offset=paging.offset,
    )
