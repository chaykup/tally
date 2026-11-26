"""Response models for the analytics API.

Money is Decimal, which FastAPI sends as a JSON string ("49.95") so cents are never
rounded. Convert with Number(...) / parseFloat(...) on the client if a chart needs it.
All dates are UTC calendar days.
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class Summary(BaseModel):
    as_of: datetime
    revenue_this_month: Decimal
    revenue_last_month: Decimal
    orders_this_month: int
    pending_orders: int
    unpaid_invoice_count: int
    unpaid_invoice_total: Decimal
    overdue_invoice_count: int
    overdue_invoice_total: Decimal
    low_stock_count: int


class MonthlyRevenue(BaseModel):
    month: date  # first day of the month
    order_count: int
    units_sold: int
    revenue: Decimal


class ProductSales(BaseModel):
    item_id: int
    sku: str
    item_name: str
    order_count: int
    units_sold: int
    revenue: Decimal


class OrderLineFact(BaseModel):
    order_id: int
    order_date: datetime
    order_day_utc: date
    order_status: str
    counts_as_revenue: bool
    customer_id: int
    customer_name: str
    sales_rep_id: int
    sales_rep_email: str
    item_id: int
    sku: str
    item_name: str
    warehouse_id: int
    warehouse_name: str
    location_code: str
    quantity: int
    unit_price: Decimal
    line_total: Decimal


class PipelineStatus(BaseModel):
    status: str
    order_count: int
    avg_hours_to_confirm: Decimal | None
    median_hours_to_confirm: Decimal | None
    avg_hours_to_invoice: Decimal | None


class OrderCycleTime(BaseModel):
    order_id: int
    order_date: datetime
    current_status: str
    confirmed_at: datetime | None
    invoiced_at: datetime | None
    cancelled_at: datetime | None
    hours_to_confirm: Decimal | None
    hours_to_invoice: Decimal | None


class OrderStatusChange(BaseModel):
    history_id: int
    order_id: int
    from_status: str | None  # None when the order was created
    to_status: str
    changed_at: datetime
    changed_day_utc: date
    changed_by: int | None


class UnpaidInvoice(BaseModel):
    invoice_id: int
    invoice_number: str
    order_id: int
    customer_id: int
    customer_name: str
    amount: Decimal
    issue_date: datetime
    due_date: date
    is_overdue: bool
    days_overdue: int


class LowStockItem(BaseModel):
    item_id: int
    sku: str
    item_name: str
    warehouse_id: int
    warehouse_name: str
    quantity: int
    reorder_threshold: int
    shortfall: int
    last_update_at: datetime


class DailyStockLevel(BaseModel):
    item_id: int
    sku: str
    item_name: str
    warehouse_id: int
    warehouse_name: str
    day: date
    closing_quantity: int
    reorder_threshold: int
    at_or_below_threshold: bool


class StockMovement(BaseModel):
    movement_id: int
    created_at: datetime
    movement_day_utc: date
    item_id: int
    sku: str
    item_name: str
    warehouse_id: int
    warehouse_name: str
    reason: str
    quantity_change: int
    quantity_after: int
    order_id: int | None
