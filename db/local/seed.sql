-- LOCAL DOCKER ONLY. Sample data so every service has something to work with.
-- Service tests rely on these rows (see shared/tally_common/testing.py); update both together.
--
-- Logins (password for all: password)
--   admin@tally.test  admin     user_id 1
--   rep@tally.test    sales     user_id 2
--   cust@tally.test   customer  user_id 3

BEGIN;

INSERT INTO accounts.users (user_id, email, password_hash, role) VALUES
    (1, 'admin@tally.test', '$argon2id$v=19$m=65536,t=3,p=4$OdyoNwNi1tLLPi9EZBYEVQ$LjbIich+XsJoH6lZwdjAOVJWMayIODo0026Jiyo5YTc', 'admin'),
    (2, 'rep@tally.test',   '$argon2id$v=19$m=65536,t=3,p=4$OdyoNwNi1tLLPi9EZBYEVQ$LjbIich+XsJoH6lZwdjAOVJWMayIODo0026Jiyo5YTc', 'sales'),
    (3, 'cust@tally.test',  '$argon2id$v=19$m=65536,t=3,p=4$OdyoNwNi1tLLPi9EZBYEVQ$LjbIich+XsJoH6lZwdjAOVJWMayIODo0026Jiyo5YTc', 'customer');

INSERT INTO inventory.products (item_id, item_name, unit_price, sku, is_active) VALUES
    (1, 'Widget',         9.99, 'WID-001', true),
    (2, 'Gadget',        24.50, 'GAD-001', true),
    (3, 'Old Doohickey',  4.00, 'OLD-001', false);   -- discontinued

INSERT INTO inventory.warehouses (warehouse_id, warehouse_name, location_code) VALUES
    (1, 'Los Angeles', 'LA-01'),
    (2, 'New York',    'NY-01');

INSERT INTO inventory.stock (item_id, warehouse_id, quantity, reorder_threshold) VALUES
    (1, 1, 120, 20),
    (1, 2,  40, 10),
    (2, 1,   3, 10),   -- below threshold: shows in analytics.low_stock
    (3, 1,   0,  5);   -- inactive product: excluded from low_stock

INSERT INTO sales.customers (customer_id, customer_name, email, user_id, sales_rep_id) VALUES
    (1, 'Acme Corp', 'orders@acme.test', 3, 2);

-- One order placed the way the transactions service should: label the stock change, take the
-- units, write the line, move the status along.
SELECT set_config('tally.user_id', '2', true);
INSERT INTO sales.orders (order_id, customer_id, created_by, delivery_address)
    VALUES (1, 1, 2, '1 Acme Way, Los Angeles, CA');
SELECT set_config('tally.movement_reason', 'sale', true), set_config('tally.order_id', '1', true);
UPDATE inventory.stock SET quantity = quantity - 5 WHERE item_id = 1 AND warehouse_id = 1;
INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 5, 9.99);
UPDATE sales.orders SET status = 'confirmed' WHERE order_id = 1;

-- Seed rows used explicit ids; move the identity counters past them.
SELECT setval(pg_get_serial_sequence('accounts.users',       'user_id'),      100);
SELECT setval(pg_get_serial_sequence('inventory.products',   'item_id'),      100);
SELECT setval(pg_get_serial_sequence('inventory.warehouses', 'warehouse_id'), 100);
SELECT setval(pg_get_serial_sequence('sales.customers',      'customer_id'),  100);
SELECT setval(pg_get_serial_sequence('sales.orders',         'order_id'),     100);

COMMIT;
