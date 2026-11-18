from fastapi.testclient import TestClient

from app.main import app
from tally_common.testing import auth_header, requires_db

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "analytics"}


@requires_db
def test_low_stock_lists_seeded_low_item():
    response = client.get("/reports/low-stock", headers=auth_header("sales"))
    assert response.status_code == 200
    assert [r["sku"] for r in response.json()] == ["GAD-001"]


@requires_db
def test_reports_are_staff_only():
    assert client.get("/reports/low-stock", headers=auth_header("customer")).status_code == 403
