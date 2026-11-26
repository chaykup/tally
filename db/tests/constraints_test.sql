-- Constraint tests for db/ddl.sql. Run against a database where ddl.sql has already been loaded:
--   psql -v ON_ERROR_STOP=1 -f db/tests/constraints_test.sql
-- Any failed assertion raises an exception, which makes psql exit non-zero and fails CI.
-- Everything runs inside a transaction that is rolled back, so the database is left empty.

\set ON_ERROR_STOP on
BEGIN;
\ir helpers.sql

-- schemas ----------------------------------------------------------------------
SELECT pg_temp.expect('every table is in its service schema',
    (SELECT array_agg(table_schema || '.' || table_name ORDER BY table_schema, table_name)
       FROM information_schema.tables
      WHERE table_type = 'BASE TABLE'
        AND table_schema IN ('public', 'core', 'accounts', 'inventory', 'sales', 'analytics'))
    = ARRAY['accounts.users',
            'inventory.products', 'inventory.stock', 'inventory.stock_movements', 'inventory.warehouses',
            'sales.customers', 'sales.invoices', 'sales.order_lines', 'sales.order_status_history',
            'sales.orders']);

-- Fixtures: valid data in every table (also proves the happy path works) ------

INSERT INTO accounts.users (user_id, email, password_hash, role) VALUES
    (1, 'admin@tally.test', 'x', 'admin'),
    (2, 'rep@tally.test',   'x', 'sales'),
    (3, 'cust@tally.test',  'x', 'customer');
INSERT INTO inventory.products (item_id, item_name, unit_price, sku) VALUES (1, 'Widget', 9.99, 'W-1');
INSERT INTO inventory.warehouses (warehouse_id, warehouse_name, location_code) VALUES
    (1, 'Main', 'LA-01'),
    (2, 'East', 'NY-01');
INSERT INTO inventory.stock (item_id, warehouse_id, quantity, reorder_threshold) VALUES (1, 1, 5, 2);
INSERT INTO sales.customers (customer_id, customer_name, email, user_id, sales_rep_id)
    VALUES (1, 'Acme', 'acme@tally.test', 3, 2);
INSERT INTO sales.orders (order_id, customer_id, created_by, delivery_address) VALUES (1, 1, 2, '1 Main St');
INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 2, 9.99);
INSERT INTO sales.invoices (order_id, invoice_number, due_date, amount) VALUES (1, 'INV-0001', '2026-12-31', 19.98);

-- Fixtures used explicit IDs, so move identity counters past them. Otherwise a later insert
-- could collide on the primary key and "pass" a unique test for the wrong reason.
SELECT setval(pg_get_serial_sequence('accounts.users',           'user_id'),      1000);
SELECT setval(pg_get_serial_sequence('inventory.products',   'item_id'),      1000);
SELECT setval(pg_get_serial_sequence('inventory.warehouses', 'warehouse_id'), 1000);
SELECT setval(pg_get_serial_sequence('sales.customers',      'customer_id'),  1000);
SELECT setval(pg_get_serial_sequence('sales.orders',         'order_id'),     1000);

SELECT pg_temp.expect('fixtures inserted', (SELECT count(*) FROM sales.invoices) = 1);
SELECT pg_temp.expect('order status defaults to pending',
    (SELECT status FROM sales.orders WHERE order_id = 1) = 'pending');

-- users ------------------------------------------------------------------------
SELECT pg_temp.expect_error('users: duplicate email',
    $q$INSERT INTO accounts.users (email, password_hash, role) VALUES ('rep@tally.test', 'x', 'sales')$q$, '23505');
SELECT pg_temp.expect_error('users: invalid role',
    $q$INSERT INTO accounts.users (email, password_hash, role) VALUES ('new@tally.test', 'x', 'manager')$q$, '22P02');
SELECT pg_temp.expect_error('users: missing password_hash',
    $q$INSERT INTO accounts.users (email, role) VALUES ('new@tally.test', 'sales')$q$, '23502');

-- products ---------------------------------------------------------------------
SELECT pg_temp.expect_error('products: duplicate sku',
    $q$INSERT INTO inventory.products (item_name, unit_price, sku) VALUES ('Copy', 1, 'W-1')$q$, '23505');
SELECT pg_temp.expect_error('products: negative price',
    $q$INSERT INTO inventory.products (item_name, unit_price, sku) VALUES ('Bad', -1, 'B-1')$q$, '23514');
SELECT pg_temp.expect_error('products: hard delete blocked while referenced',
    $q$DELETE FROM inventory.products WHERE item_id = 1$q$, '23503');

-- warehouses -------------------------------------------------------------------
SELECT pg_temp.expect_error('warehouses: duplicate location_code',
    $q$INSERT INTO inventory.warehouses (warehouse_name, location_code) VALUES ('Dup', 'LA-01')$q$, '23505');

-- stock ------------------------------------------------------------------------
SELECT pg_temp.expect_error('stock: quantity cannot go negative (oversell guard)',
    $q$UPDATE inventory.stock SET quantity = quantity - 6 WHERE item_id = 1 AND warehouse_id = 1$q$, '23514');
SELECT pg_temp.expect_error('stock: negative reorder_threshold',
    $q$UPDATE inventory.stock SET reorder_threshold = -1 WHERE item_id = 1$q$, '23514');
SELECT pg_temp.expect_error('stock: duplicate product+warehouse row',
    $q$INSERT INTO inventory.stock (item_id, warehouse_id, quantity) VALUES (1, 1, 3)$q$, '23505');
SELECT pg_temp.expect_error('stock: unknown product',
    $q$INSERT INTO inventory.stock (item_id, warehouse_id, quantity) VALUES (999, 1, 3)$q$, '23503');
SELECT pg_temp.expect_error('stock: unknown warehouse',
    $q$INSERT INTO inventory.stock (item_id, warehouse_id, quantity) VALUES (1, 999, 3)$q$, '23503');

-- customers --------------------------------------------------------------------
SELECT pg_temp.expect_error('customers: duplicate email',
    $q$INSERT INTO sales.customers (customer_name, email, sales_rep_id) VALUES ('X', 'acme@tally.test', 2)$q$, '23505');
SELECT pg_temp.expect_error('customers: one login per customer',
    $q$INSERT INTO sales.customers (customer_name, email, user_id, sales_rep_id) VALUES ('X', 'x@tally.test', 3, 2)$q$, '23505');
SELECT pg_temp.expect_error('customers: sales rep required',
    $q$INSERT INTO sales.customers (customer_name, email) VALUES ('X', 'x@tally.test')$q$, '23502');
SELECT pg_temp.expect_error('customers: unknown sales rep',
    $q$INSERT INTO sales.customers (customer_name, email, sales_rep_id) VALUES ('X', 'x@tally.test', 999)$q$, '23503');

-- orders -----------------------------------------------------------------------
SELECT pg_temp.expect_error('orders: unknown customer',
    $q$INSERT INTO sales.orders (customer_id, created_by, delivery_address) VALUES (999, 2, 'a')$q$, '23503');
SELECT pg_temp.expect_error('orders: unknown creator',
    $q$INSERT INTO sales.orders (customer_id, created_by, delivery_address) VALUES (1, 999, 'a')$q$, '23503');
SELECT pg_temp.expect_error('orders: invalid status',
    $q$UPDATE sales.orders SET status = 'shipped' WHERE order_id = 1$q$, '22P02');

-- order_lines ------------------------------------------------------------------
SELECT pg_temp.expect_error('order_lines: quantity must be positive',
    $q$INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 0, 9.99)$q$, '23514');
SELECT pg_temp.expect_error('order_lines: negative price',
    $q$UPDATE sales.order_lines SET unit_price = -1 WHERE order_id = 1$q$, '23514');
SELECT pg_temp.expect_error('order_lines: duplicate product+warehouse on one order',
    $q$INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 1, 9.99)$q$, '23505');
SELECT pg_temp.expect_error('order_lines: warehouse must stock the product (cross-schema FK)',
    $q$INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 2, 1, 9.99)$q$, '23503');

-- invoices ---------------------------------------------------------------------
SELECT pg_temp.expect_error('invoices: one invoice per order',
    $q$INSERT INTO sales.invoices (order_id, invoice_number, due_date, amount) VALUES (1, 'INV-0002', '2026-12-31', 1)$q$, '23505');
SELECT pg_temp.expect_error('invoices: negative amount',
    $q$UPDATE sales.invoices SET amount = -1 WHERE order_id = 1$q$, '23514');
SELECT pg_temp.expect_error('invoices: invalid status',
    $q$UPDATE sales.invoices SET status = 'refunded' WHERE order_id = 1$q$, '22P02');
SELECT pg_temp.expect_error('orders: delete blocked while invoiced',
    $q$DELETE FROM sales.orders WHERE order_id = 1$q$, '23503');

-- triggers ---------------------------------------------------------------------
UPDATE inventory.products SET updated_at = '2000-01-01' WHERE item_id = 1;  -- trigger overwrites this
SELECT pg_temp.expect('products.updated_at maintained by trigger',
    (SELECT updated_at > '2000-01-01' FROM inventory.products WHERE item_id = 1));
UPDATE inventory.stock SET last_update_at = '2000-01-01' WHERE item_id = 1;
SELECT pg_temp.expect('stock.last_update_at maintained by trigger',
    (SELECT last_update_at > '2000-01-01' FROM inventory.stock WHERE item_id = 1));

-- stock_movements (written by trigger) -----------------------------------------
SELECT pg_temp.expect('stock_movements: new stock row records an initial movement',
    (SELECT (reason, quantity_change, quantity_after) = ('initial'::inventory.movement_reason, 5, 5)
       FROM inventory.stock_movements WHERE item_id = 1 AND warehouse_id = 1));

SELECT set_config('tally.movement_reason', 'receipt', true), set_config('tally.user_id', '1', true);
UPDATE inventory.stock SET quantity = quantity + 7 WHERE item_id = 1 AND warehouse_id = 1;
SELECT pg_temp.expect('stock_movements: quantity change records reason, delta, level, user',
    (SELECT (reason, quantity_change, quantity_after, performed_by)
            = ('receipt'::inventory.movement_reason, 7, 12, 1)
       FROM inventory.stock_movements WHERE item_id = 1 ORDER BY movement_id DESC LIMIT 1));
SELECT set_config('tally.movement_reason', '', true), set_config('tally.user_id', '', true);

UPDATE inventory.stock SET quantity = quantity - 2 WHERE item_id = 1;
SELECT pg_temp.expect('stock_movements: unlabeled change defaults to adjustment',
    (SELECT (reason, quantity_change, quantity_after) = ('adjustment'::inventory.movement_reason, -2, 10)
       FROM inventory.stock_movements WHERE item_id = 1 ORDER BY movement_id DESC LIMIT 1));

UPDATE inventory.stock SET reorder_threshold = 4 WHERE item_id = 1;
UPDATE inventory.stock SET quantity = quantity WHERE item_id = 1;
SELECT pg_temp.expect('stock_movements: no movement when quantity is unchanged',
    (SELECT count(*) FROM inventory.stock_movements WHERE item_id = 1) = 3);

SELECT set_config('tally.movement_reason', 'sale', true);
SELECT pg_temp.expect_error('stock_movements: a sale must name its order',
    $q$UPDATE inventory.stock SET quantity = quantity - 1 WHERE item_id = 1$q$, '23514');
SELECT set_config('tally.order_id', '999', true);
SELECT pg_temp.expect_error('stock_movements: a sale must name a real order',
    $q$UPDATE inventory.stock SET quantity = quantity - 1 WHERE item_id = 1$q$, '23503');
SELECT set_config('tally.movement_reason', 'stolen', true);
SELECT pg_temp.expect_error('stock_movements: invalid reason',
    $q$UPDATE inventory.stock SET quantity = quantity - 1 WHERE item_id = 1$q$, '22P02');
SELECT set_config('tally.movement_reason', '', true), set_config('tally.order_id', '', true);

SELECT pg_temp.expect_error('stock_movements: stock row with history cannot be deleted',
    $q$DELETE FROM inventory.stock WHERE item_id = 1 AND warehouse_id = 1$q$, '23503');

-- order_status_history (written by trigger) ------------------------------------
SELECT pg_temp.expect('order history: creation recorded with no previous status',
    (SELECT (from_status, to_status) IS NOT DISTINCT FROM (NULL::sales.order_status, 'pending'::sales.order_status)
       FROM sales.order_status_history WHERE order_id = 1));
SELECT set_config('tally.user_id', '2', true);
UPDATE sales.orders SET status = 'confirmed' WHERE order_id = 1;
UPDATE sales.orders SET delivery_address = '2 Main St' WHERE order_id = 1;  -- not a status change
UPDATE sales.orders SET status = 'confirmed' WHERE order_id = 1;            -- same status, no row
SELECT set_config('tally.user_id', '', true);
SELECT pg_temp.expect('order history: one row per real status change, with who changed it',
    (SELECT array_agg(from_status::text || '->' || to_status::text || ' by ' || changed_by ORDER BY history_id)
       FROM sales.order_status_history WHERE from_status IS NOT NULL AND order_id = 1)
    = ARRAY['pending->confirmed by 2']);

-- cascade ----------------------------------------------------------------------
DELETE FROM sales.invoices WHERE order_id = 1;
DELETE FROM sales.orders WHERE order_id = 1;
SELECT pg_temp.expect('deleting an order cascades to its lines and status history',
    (SELECT count(*) FROM sales.order_lines WHERE order_id = 1) = 0
    AND (SELECT count(*) FROM sales.order_status_history WHERE order_id = 1) = 0);

ROLLBACK;
\echo 'All constraint tests passed.'
