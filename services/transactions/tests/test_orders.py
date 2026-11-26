from fastapi.testclient import TestClient
from sqlalchemy import text
from uuid import uuid4
from app.main import app
from tally_common.db import get_engine
from tally_common.testing import auth_header, requires_db
import pytest

client = TestClient(app)


@requires_db
def test_admin_can_list_orders():
    response = client.get(
        "/orders",
        headers=auth_header("admin"),
    )

    assert response.status_code == 200

    orders = response.json()
    assert isinstance(orders, list)

    for order in orders:
        assert "order_id" in order
        assert "customer_id" in order
        assert "status" in order
        assert isinstance(order["lines"], list)


@requires_db
def test_admin_can_get_order():
    response = client.get(
        "/orders/1",
        headers=auth_header("admin"),
    )

    assert response.status_code == 200

    order = response.json()
    assert order["order_id"] == 1
    assert order["customer_id"] == 1
    assert len(order["lines"]) >= 1


@requires_db
def test_nonexistent_order_returns_404():
    response = client.get(
        "/orders/0",
        headers=auth_header("admin"),
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Order not found"
    }


def test_unauthenticated_request_returns_401():
    response = client.get("/orders")

    assert response.status_code == 401


@requires_db
def test_create_order_deducts_inventory():
    engine = get_engine()

    # 1. Record inventory before creating the order.
    with engine.connect() as conn:
        stock_before = conn.execute(
            text("""
                SELECT quantity
                FROM inventory.stock
                WHERE item_id = 1 AND warehouse_id = 1
            """)
        ).scalar_one()

    assert stock_before >= 1

    # 2. Create an order through FastAPI.
    response = client.post(
        "/orders",
        headers=auth_header("admin"),
        json={
            "customer_id": 1,
            "delivery_address": "Automated Test Address",
            "items": [
                {
                    "item_id": 1,
                    "warehouse_id": 1,
                    "quantity": 1,
                }
            ],
        },
    )

    assert response.status_code == 201

    order = response.json()
    assert order["status"] == "pending"
    assert order["created_by"] == 1
    assert len(order["lines"]) == 1
    assert order["lines"][0]["unit_price"] == "9.99"

    # 3. Verify the inventory and audit history.
    with engine.connect() as conn:
        stock_after = conn.execute(
            text("""
                SELECT quantity
                FROM inventory.stock
                WHERE item_id = 1 AND warehouse_id = 1
            """)
        ).scalar_one()

        movement = conn.execute(
            text("""
                SELECT quantity_change, reason, performed_by
                FROM inventory.stock_movements
                WHERE order_id = :order_id
            """),
            {"order_id": order["order_id"]},
        ).mappings().one()

    assert stock_after == stock_before - 1
    assert movement["quantity_change"] == -1
    assert movement["reason"] == "sale"
    assert movement["performed_by"] == 1

@requires_db
def test_create_order_insufficient_stock():
    engine = get_engine()

    # 1. Get the current stock quantity.
    with engine.connect() as conn:
        stock_before = conn.execute(
            text("""
                SELECT quantity
                FROM inventory.stock
                WHERE item_id = 1 AND warehouse_id = 1
            """)
        ).scalar_one()

    # Request one more item than is available.
    requested_quantity = stock_before + 1

    # 2. Attempt to create the order.
    response = client.post(
        "/orders",
        headers=auth_header("admin"),
        json={
            "customer_id": 1,
            "delivery_address": "Insufficient Stock Test",
            "items": [
                {
                    "item_id": 1,
                    "warehouse_id": 1,
                    "quantity": requested_quantity,
                }
            ],
        },
    )

    # 3. Verify the request was rejected.
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Insufficient stock"
    }

    # 4. Verify no database changes occurred.
    with engine.connect() as conn:
        stock_after = conn.execute(
            text("""
                SELECT quantity
                FROM inventory.stock
                WHERE item_id = 1 AND warehouse_id = 1
            """)
        ).scalar_one()

        order_count = conn.execute(
            text("""
                SELECT COUNT(*)
                FROM sales.orders
                WHERE delivery_address =
                    'Insufficient Stock Test'
            """)
        ).scalar_one()

    assert stock_after == stock_before
    assert order_count == 0

@pytest.mark.parametrize("quantity", [0, -1])
def test_create_order_invalid_quantity(quantity):
    response = client.post(
        "/orders",
        headers=auth_header("admin"),
        json={
            "customer_id": 1,
            "delivery_address": "Invalid Quantity Test",
            "items": [
                {
                    "item_id": 1,
                    "warehouse_id": 1,
                    "quantity": quantity,
                }
            ],
        },
    )

    assert response.status_code == 422

    errors = response.json()["detail"]

    assert any(
        error["loc"] == ["body", "items", 0, "quantity"]
        for error in errors
    )


@requires_db
def test_customer_can_list_own_orders():
    response = client.get(
        "/orders",
        headers=auth_header("customer"),
    )

    assert response.status_code == 200

    orders = response.json()
    assert len(orders) >= 1

    # All returned orders belong to customer ID 1.
    assert all(
        order["customer_id"] == 1
        for order in orders
    )


@requires_db
def test_customer_can_get_own_order():
    response = client.get(
        "/orders/1",
        headers=auth_header("customer"),
    )

    assert response.status_code == 200
    assert response.json()["customer_id"] == 1


@requires_db
def test_sales_can_get_assigned_customer_order():
    response = client.get(
        "/orders/1",
        headers=auth_header("sales"),
    )

    assert response.status_code == 200
    assert response.json()["order_id"] == 1


def test_customer_cannot_confirm_order():
    response = client.patch(
        "/orders/1/status",
        headers=auth_header("customer"),
        json={"status": "confirmed"},
    )

    assert response.status_code == 403


def test_customer_cannot_cancel_order():
    response = client.post(
        "/orders/1/cancel",
        headers=auth_header("customer"),
    )

    assert response.status_code == 403


@pytest.fixture
def other_customer_order():
    engine = get_engine()

    # Create a temporary customer and order.
    with engine.begin() as conn:
        customer_id = conn.execute(
            text("""
                INSERT INTO sales.customers (
                    customer_name,
                    email,
                    sales_rep_id
                )
                VALUES (
                    'Authorization Test Customer',
                    :email,
                    2
                )
                RETURNING customer_id
            """),
            {"email": f"auth-{uuid4().hex}@test.local"},
        ).scalar_one()

        order_id = conn.execute(
            text("""
                INSERT INTO sales.orders (
                    customer_id,
                    created_by,
                    delivery_address
                )
                VALUES (
                    :customer_id,
                    1,
                    'Authorization Test Address'
                )
                RETURNING order_id
            """),
            {"customer_id": customer_id},
        ).scalar_one()

    try:
        yield customer_id, order_id

    finally:
        # Remove temporary test records.
        with engine.begin() as conn:
            conn.execute(
                text("""
                    DELETE FROM sales.orders
                    WHERE order_id = :order_id
                """),
                {"order_id": order_id},
            )

            conn.execute(
                text("""
                    DELETE FROM sales.customers
                    WHERE customer_id = :customer_id
                """),
                {"customer_id": customer_id},
            )


@requires_db
def test_customer_cannot_access_other_orders(
    other_customer_order,
):
    customer_id, order_id = other_customer_order

    # Admin should be able to access the order.
    admin_response = client.get(
        f"/orders/{order_id}",
        headers=auth_header("admin"),
    )

    assert admin_response.status_code == 200

    # Seeded customer user 3 does not own this account.
    response = client.get(
        f"/orders/{order_id}",
        headers=auth_header("customer"),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Order not found"

    # The order must also be excluded from their list.
    list_response = client.get(
        "/orders",
        headers=auth_header("customer"),
    )

    assert list_response.status_code == 200

    assert all(
        order["order_id"] != order_id
        for order in list_response.json()
    )

    # The customer must not create orders for this account.
    create_response = client.post(
        "/orders",
        headers=auth_header("customer"),
        json={
            "customer_id": customer_id,
            "delivery_address": "Unauthorized Test",
            "items": [
                {
                    "item_id": 1,
                    "warehouse_id": 1,
                    "quantity": 1,
                }
            ],
        },
    )

    assert create_response.status_code == 403