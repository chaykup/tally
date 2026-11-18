# Transactions service

Port **8003**. Owns schema **`sales`**: customers, orders, order_lines, invoices, and
order_status_history (read-only). DB login: `tally_transactions` (role `sales_service`).

Can read the inventory catalog and stock, and can change **only** `inventory.stock.quantity`.
That is exactly what placing an order needs, done in **one transaction**:

1. `set_change_context(session, movement_reason="sale", order_id=order.order_id, user_id=user.user_id)`
2. Lock the stock rows: `select(Stock).where(...).with_for_update()`
3. Decrement `quantity`. The database rejects overselling (`CHECK quantity >= 0`).
4. Insert the order lines with `unit_price` copied from the product, then commit.

Cancelling an order reverses this with `movement_reason="sale_cancelled"`. Status changes
are recorded in `sales.order_status_history` automatically. Pass `user_id` in
`set_change_context` to record who made them.

The `Order` / `OrderLine` models from the `feat/orders` branch go in `app/models.py`. That
file's docstring lists what to change when moving them (schema names, foreign keys).

**Done:** `GET /customers` (example endpoint: reps see their own customers, admins see all).

**To do:** orders (place, confirm, cancel), invoices (issue, mark paid, void), customer CRUD.
