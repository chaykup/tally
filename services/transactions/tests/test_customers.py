from fastapi.testclient import TestClient

from app.main import app
from tally_common.testing import auth_header, requires_db

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "transactions"}


@requires_db
def test_sales_rep_sees_own_customers():
    response = client.get("/customers", headers=auth_header("sales"))
    assert response.status_code == 200
    assert [c["customer_name"] for c in response.json()] == ["Acme Corp"]


@requires_db
def test_customers_cannot_list_customers():
    assert client.get("/customers", headers=auth_header("customer")).status_code == 403
