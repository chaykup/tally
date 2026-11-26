from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Order, OrderLine, OrderStatus
from app.order_schemas import OrderResponse, OrderCreate, OrderStatusUpdate
from tally_common.db import get_session
from tally_common.security import CurrentUser, require_roles
from tally_common.audit import set_change_context

router = APIRouter(prefix="/orders", tags=["orders"])


def scoped_orders(user: CurrentUser):
    """Restrict orders according to the authenticated user's role."""

    query = select(Order)

    if user.role == "admin":
        return query

    query = query.join(
        Customer,
        Order.customer_id == Customer.customer_id,
    )

    if user.role == "sales":
        return query.where(
            Customer.sales_rep_id == user.user_id
        )

    return query.where(
        Customer.user_id == user.user_id
    )


@router.get("", response_model=list[OrderResponse])
def list_orders(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: CurrentUser = Depends(
        require_roles("admin", "sales", "customer")
    ),
    session: Session = Depends(get_session),
):
    query = (
        scoped_orders(user)
        .options(selectinload(Order.lines))
        .order_by(Order.order_id.desc())
        .offset(offset)
        .limit(limit)
    )

    return session.scalars(query).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    user: CurrentUser = Depends(
        require_roles("admin", "sales", "customer")
    ),
    session: Session = Depends(get_session),
):
    query = (
        scoped_orders(user)
        .where(Order.order_id == order_id)
        .options(selectinload(Order.lines))
    )

    order = session.scalar(query)

    if order is None:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return order



@router.post("", response_model=OrderResponse, status_code=201)
def create_order(
    data: OrderCreate,
    user: CurrentUser = Depends(
        require_roles("admin", "sales", "customer")
    ),
    session: Session = Depends(get_session),
):
    # Prevent duplicate product/warehouse combinations.
    keys = [(i.item_id, i.warehouse_id) for i in data.items]

    if len(keys) != len(set(keys)):
        raise HTTPException(
            status_code=422,
            detail="Duplicate product and warehouse combination",
        )

    with session.begin():
        # 1. Validate the customer and permissions.
        customer = session.get(Customer, data.customer_id)

        if customer is None:
            raise HTTPException(404, "Customer not found")

        if user.role == "sales":
            if customer.sales_rep_id != user.user_id:
                raise HTTPException(403, "Customer not assigned to you")

        if user.role == "customer":
            if customer.user_id != user.user_id:
                raise HTTPException(403, "Not your customer account")

        # 2. Lock inventory rows in a consistent order.
        prices = {}

        for item_id, warehouse_id in sorted(keys):
            row = session.execute(
                text("""
                    SELECT
                        s.quantity,
                        p.unit_price,
                        p.is_active
                    FROM inventory.stock AS s
                    JOIN inventory.products AS p
                      ON p.item_id = s.item_id
                    WHERE s.item_id = :item_id
                      AND s.warehouse_id = :warehouse_id
                    FOR UPDATE OF s
                """),
                {
                    "item_id": item_id,
                    "warehouse_id": warehouse_id,
                },
            ).mappings().first()

            if row is None:
                raise HTTPException(
                    404, "Product not stocked at this warehouse"
                )

            if not row["is_active"]:
                raise HTTPException(409, "Product is inactive")

            requested = next(
                i.quantity for i in data.items
                if (i.item_id, i.warehouse_id)
                == (item_id, warehouse_id)
            )

            if row["quantity"] < requested:
                raise HTTPException(409, "Insufficient stock")

            prices[(item_id, warehouse_id)] = row["unit_price"]

        # 3. Record who is creating the order.
        set_change_context(session, user_id=user.user_id)

        order = Order(
            customer_id=data.customer_id,
            created_by=user.user_id,
            delivery_address=data.delivery_address,
        )
        session.add(order)
        session.flush()

        # 4. Label the stock movements for database triggers.
        set_change_context(
            session,
            user_id=user.user_id,
            movement_reason="sale",
            order_id=order.order_id,
        )

        # 5. Create lines and deduct inventory.
        for item in data.items:
            session.add(
                OrderLine(
                    order_id=order.order_id,
                    item_id=item.item_id,
                    warehouse_id=item.warehouse_id,
                    quantity=item.quantity,
                    unit_price=prices[
                        (item.item_id, item.warehouse_id)
                    ],
                )
            )

            session.execute(
                text("""
                    UPDATE inventory.stock
                    SET quantity = quantity - :quantity
                    WHERE item_id = :item_id
                      AND warehouse_id = :warehouse_id
                """),
                {
                    "quantity": item.quantity,
                    "item_id": item.item_id,
                    "warehouse_id": item.warehouse_id,
                },
            )

        session.flush()
        new_order_id = order.order_id

    # Transaction committed successfully.
    # Reuse the existing GET endpoint's eager loading pattern.
    query = (
        select(Order)
        .where(Order.order_id == new_order_id)
        .options(selectinload(Order.lines))
    )

    return session.scalar(query)

@router.patch(
    "/{order_id}/status",
    response_model=OrderResponse,
    responses={
        403: {"description": "Forbidden"},
        404: {"description": "Order not found"},
        409: {"description": "Invalid status transition"},
    },
)
def update_order_status(
    order_id: int,
    data: OrderStatusUpdate,
    user: CurrentUser = Depends(
        require_roles("admin", "sales")
    ),
    session: Session = Depends(get_session),
):
    with session.begin():

        # 1. Retrieve and lock the order.
        query = (
            scoped_orders(user)
            .where(Order.order_id == order_id)
            .with_for_update(of=Order)
        )

        order = session.scalar(query)

        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        # 2. Only pending orders can be confirmed.
        if order.status != OrderStatus.pending:
            raise HTTPException(
                status_code=409,
                detail="Only pending orders can be confirmed",
            )

        # 3. Record the user performing the change.
        set_change_context(
            session,
            user_id=user.user_id,
        )

        # 4. Update the order status.
        order.status = OrderStatus(data.status)

        session.flush()

    # 5. The transaction has committed.
    # Retrieve the order and its related lines.
    query = (
        select(Order)
        .where(Order.order_id == order_id)
        .options(selectinload(Order.lines))
    )

    return session.scalar(query)

@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    responses={
        404: {"description": "Order not found"},
        409: {"description": "Order cannot be cancelled"},
    },
)
def cancel_order(
    order_id: int,
    user: CurrentUser = Depends(
        require_roles("admin", "sales")
    ),
    session: Session = Depends(get_session),
):
    with session.begin():

        # 1. Lock the order and load its line items.
        query = (
            scoped_orders(user)
            .where(Order.order_id == order_id)
            .options(selectinload(Order.lines))
            .with_for_update(of=Order)
        )

        order = session.scalar(query)

        if order is None:
            raise HTTPException(
                status_code=404,
                detail="Order not found",
            )

        # 2. Validate the current status.
        if order.status not in (
            OrderStatus.pending,
            OrderStatus.confirmed,
        ):
            raise HTTPException(
                status_code=409,
                detail="Order cannot be cancelled",
            )

        # 3. Lock inventory rows in a consistent order.
        lines = sorted(
            order.lines,
            key=lambda line: (
                line.item_id,
                line.warehouse_id,
            ),
        )

        for line in lines:
            stock = session.execute(
                text("""
                    SELECT quantity
                    FROM inventory.stock
                    WHERE item_id = :item_id
                      AND warehouse_id = :warehouse_id
                    FOR UPDATE
                """),
                {
                    "item_id": line.item_id,
                    "warehouse_id": line.warehouse_id,
                },
            ).first()

            if stock is None:
                raise HTTPException(
                    status_code=409,
                    detail="Order stock record not found",
                )

        # 4. Set audit information for PostgreSQL triggers.
        set_change_context(
            session,
            user_id=user.user_id,
            movement_reason="sale_cancelled",
            order_id=order.order_id,
        )

        # 5. Restore purchased quantities.
        for line in lines:
            session.execute(
                text("""
                    UPDATE inventory.stock
                    SET quantity = quantity + :quantity
                    WHERE item_id = :item_id
                      AND warehouse_id = :warehouse_id
                """),
                {
                    "quantity": line.quantity,
                    "item_id": line.item_id,
                    "warehouse_id": line.warehouse_id,
                },
            )

        # 6. Update the order status.
        order.status = OrderStatus.cancelled

        session.flush()

    # 7. Return the updated order after committing.
    query = (
        select(Order)
        .where(Order.order_id == order_id)
        .options(selectinload(Order.lines))
    )

    return session.scalar(query)