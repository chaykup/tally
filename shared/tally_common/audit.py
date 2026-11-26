"""Labels for the history the database records automatically.

Database triggers write inventory.stock_movements on every stock quantity change and
sales.order_status_history on every order status change. Call set_change_context in the
same transaction, before the UPDATE, so those rows say why and who:

    set_change_context(session, user_id=user.user_id, movement_reason="sale", order_id=order.order_id)
    stock.quantity -= line.quantity
    session.commit()

The values last until the transaction commits or rolls back.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

MOVEMENT_REASONS = {"initial", "receipt", "sale", "sale_cancelled", "adjustment", "transfer"}


def set_change_context(
    session: Session,
    *,
    user_id: int | None = None,
    movement_reason: str | None = None,
    order_id: int | None = None,
) -> None:
    if movement_reason is not None and movement_reason not in MOVEMENT_REASONS:
        raise ValueError(f"unknown movement_reason {movement_reason!r}")
    values = {
        "tally.user_id": user_id,
        "tally.movement_reason": movement_reason,
        "tally.order_id": order_id,
    }
    for name, value in values.items():
        session.execute(
            text("SELECT set_config(:name, :value, true)"),
            {"name": name, "value": "" if value is None else str(value)},
        )
