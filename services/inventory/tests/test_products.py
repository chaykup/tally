from fastapi.testclient import TestClient

from app.main import app
from tally_common.testing import auth_header, requires_db

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "inventory"}


def test_products_require_login():
    assert client.get("/products").status_code == 401


@requires_db
def test_list_products_returns_active_seed_products():
    response = client.get("/products", headers=auth_header("sales"))
    assert response.status_code == 200
    skus = [p["sku"] for p in response.json()]
    assert "WID-001" in skus
    assert "OLD-001" not in skus  # inactive
