# Inventory service

Port **8002**. Owns schema **`inventory`**: products, warehouses, stock, and stock_movements
(read-only). DB login: `tally_inventory` (role `inventory_service`).

- Products are soft-deleted with `is_active = false`, because order lines keep pointing at them.
- A stock row with movement history can't be deleted. Set its quantity to 0 instead.
- Every change to `stock.quantity` is recorded in `inventory.stock_movements` by a trigger.
  Label each change before you make it:
  `set_change_context(session, movement_reason="receipt" | "adjustment" | "transfer", user_id=...)`.

**Done:** `GET /products` (example endpoint).

**To do:** create and update products and warehouses, stock receipts, adjustments,
transfers between warehouses, and a stock lookup per product.
