"""Report contents, checked against db/local/seed.sql.

Seed data in brief:
  order 1  confirmed  5 x WID-001 @ 9.99 from LA-01 (warehouse 1)   = 49.95
  order 2  invoiced   3 x WID-001 @ 9.99 from NY-01 (warehouse 2)   = 29.97, invoice 10 days overdue
  stock    WID-001 LA 120 -> 115, NY 40 -> 37; GAD-001 LA 3 (threshold 10); OLD-001 inactive

These tests assume an unmodified seed. If you've added data locally, reset with
`docker compose down -v && docker compose up -d --build`.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app
from tally_common.testing import auth_header, requires_db

client = TestClient(app)
STAFF = auth_header("sales")


def get(path: str):
    response = client.get(path, headers=STAFF)
    assert response.status_code == 200, response.text
    return response.json()


def today() -> date:
    return datetime.now(timezone.utc).date()


@requires_db
def test_admin_can_read_reports_too():
    assert client.get("/reports/summary", headers=auth_header("admin")).status_code == 200


@requires_db
def test_summary_matches_the_detailed_reports():
    summary = get("/reports/summary")
    this_month = today().replace(day=1).isoformat()
    months = {m["month"]: m for m in get("/reports/revenue-by-month")}

    assert Decimal(summary["revenue_this_month"]) == Decimal(months[this_month]["revenue"])
    assert summary["orders_this_month"] == months[this_month]["order_count"]
    assert summary["pending_orders"] == 0
    assert summary["unpaid_invoice_count"] == summary["overdue_invoice_count"] == 1
    assert Decimal(summary["unpaid_invoice_total"]) == Decimal(summary["overdue_invoice_total"]) == Decimal("29.97")
    assert summary["low_stock_count"] == 1


@requires_db
def test_revenue_by_month_fills_empty_months_with_zero():
    months = get("/reports/revenue-by-month?start=2020-01-15&end=2020-03-01")
    assert [m["month"] for m in months] == ["2020-01-01", "2020-02-01", "2020-03-01"]
    assert all(m["order_count"] == 0 and m["revenue"] == "0.00" for m in months)


@requires_db
def test_revenue_by_month_includes_seeded_orders():
    months = get("/reports/revenue-by-month")
    assert months[-1]["month"] == today().replace(day=1).isoformat()  # runs through the current month
    seeded = [m for m in months if m["order_count"]]
    assert len(seeded) == 1
    assert seeded[0]["order_count"] == 2
    assert seeded[0]["units_sold"] == 8
    assert Decimal(seeded[0]["revenue"]) == Decimal("79.92")


@requires_db
def test_top_products():
    products = get("/reports/top-products")
    assert products == [
        {"item_id": 1, "sku": "WID-001", "item_name": "Widget", "order_count": 2, "units_sold": 8, "revenue": "79.92"}
    ]
    assert get("/reports/top-products?start=2020-01-01&end=2020-12-31") == []


@requires_db
def test_order_lines_filters():
    lines = get("/reports/order-lines")
    assert len(lines) == 2
    assert {line["warehouse_id"] for line in lines} == {1, 2}

    invoiced = get("/reports/order-lines?status=invoiced")
    assert [(line["order_id"], line["quantity"], line["line_total"]) for line in invoiced] == [(2, 3, "29.97")]
    assert invoiced[0]["sales_rep_email"] == "rep@tally.test"

    assert len(get("/reports/order-lines?limit=1")) == 1
    assert get("/reports/order-lines?item_id=2") == []


@requires_db
def test_order_pipeline():
    pipeline = {p["status"]: p for p in get("/reports/order-pipeline")}
    assert set(pipeline) == {"confirmed", "invoiced"}
    assert pipeline["confirmed"]["order_count"] == pipeline["invoiced"]["order_count"] == 1
    # Seed orders move through their statuses in one transaction, so it takes 0 hours.
    assert Decimal(pipeline["invoiced"]["avg_hours_to_invoice"]) == 0
    assert pipeline["confirmed"]["avg_hours_to_invoice"] is None


@requires_db
def test_order_cycle_times():
    cycles = {c["order_id"]: c for c in get("/reports/order-cycle-times")}
    assert cycles[1]["current_status"] == "confirmed" and cycles[1]["invoiced_at"] is None
    assert cycles[2]["current_status"] == "invoiced" and cycles[2]["invoiced_at"] is not None
    assert [c["order_id"] for c in get("/reports/order-cycle-times?status=invoiced")] == [2]


@requires_db
def test_order_status_changes_timeline():
    changes = get("/reports/order-status-changes?order_id=2")
    timeline = [(c["from_status"], c["to_status"]) for c in reversed(changes)]  # oldest first
    assert timeline == [(None, "pending"), ("pending", "confirmed"), ("confirmed", "invoiced")]
    assert all(c["changed_by"] == 2 for c in changes)  # seed sets tally.user_id to the rep


@requires_db
def test_unpaid_invoices():
    invoices = get("/reports/unpaid-invoices")
    assert len(invoices) == 1
    invoice = invoices[0]
    assert (invoice["invoice_number"], invoice["amount"], invoice["customer_name"]) == ("INV-0001", "29.97", "Acme Corp")
    assert invoice["is_overdue"] and invoice["days_overdue"] >= 10
    assert get("/reports/unpaid-invoices?overdue_only=true") == invoices
    assert get("/reports/unpaid-invoices?customer_id=999") == []


@requires_db
def test_low_stock():
    rows = get("/reports/low-stock")
    assert [(r["sku"], r["quantity"], r["reorder_threshold"], r["shortfall"]) for r in rows] == [("GAD-001", 3, 10, 7)]
    assert get("/reports/low-stock?warehouse_id=2") == []


@requires_db
def test_stock_levels_default_to_last_30_days_and_end_at_current_stock():
    levels = get("/reports/stock-levels?item_id=1&warehouse_id=1")
    assert 1 <= len(levels) <= 30
    assert levels[-1]["day"] == today().isoformat()
    assert levels[-1]["closing_quantity"] == 115


@requires_db
def test_stock_levels_cover_every_stock_row():
    levels = get(f"/reports/stock-levels?start={today().isoformat()}")
    assert {(r["sku"], r["warehouse_id"], r["closing_quantity"]) for r in levels} == {
        ("WID-001", 1, 115), ("WID-001", 2, 37), ("GAD-001", 1, 3), ("OLD-001", 1, 0),
    }


@requires_db
def test_stock_movements():
    moves = get("/reports/stock-movements?item_id=1&warehouse_id=1")
    assert [(m["reason"], m["quantity_change"], m["quantity_after"], m["order_id"]) for m in moves] == [
        ("sale", -5, 115, 1),
        ("initial", 120, 120, None),
    ]
    sales = get("/reports/stock-movements?reason=sale")
    assert sorted(m["order_id"] for m in sales) == [1, 2]
