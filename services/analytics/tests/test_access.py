"""Access control and input validation. None of these reach the database."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tally_common.testing import auth_header

client = TestClient(app)

REPORTS = [
    "/reports/summary",
    "/reports/revenue-by-month",
    "/reports/top-products",
    "/reports/order-lines",
    "/reports/order-pipeline",
    "/reports/order-cycle-times",
    "/reports/order-status-changes",
    "/reports/unpaid-invoices",
    "/reports/low-stock",
    "/reports/stock-levels",
    "/reports/stock-movements",
]


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "analytics"}


def test_every_report_route_is_listed_here():
    routes = {path for path in app.openapi()["paths"] if path.startswith("/reports")}
    assert routes == set(REPORTS)


@pytest.mark.parametrize("path", REPORTS)
def test_reports_require_login(path):
    assert client.get(path).status_code == 401


@pytest.mark.parametrize("path", REPORTS)
def test_reports_are_staff_only(path):
    assert client.get(path, headers=auth_header("customer")).status_code == 403


@pytest.mark.parametrize(
    "path",
    [
        "/reports/revenue-by-month?start=2026-03-01&end=2026-01-01",
        "/reports/top-products?start=2026-03-01&end=2026-01-01",
        "/reports/stock-levels?start=2026-03-01&end=2026-01-01",
        "/reports/stock-levels?start=2024-01-01&end=2026-01-01",   # longer than 366 days
        "/reports/top-products?limit=0",
        "/reports/top-products?sort_by=price",
        "/reports/order-lines?status=shipped",
        "/reports/order-lines?limit=5000",
        "/reports/stock-movements?reason=stolen",
        "/reports/stock-movements?start=not-a-date",
    ],
)
def test_bad_parameters_are_422(path):
    assert client.get(path, headers=auth_header("sales")).status_code == 422
