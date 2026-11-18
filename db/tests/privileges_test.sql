-- Privilege tests: each service role can do its own job and nothing outside it.
-- Run against a database where ddl.sql has already been loaded, as a superuser
-- (or the schema owner) so the test can SET ROLE to each service:
--   psql -v ON_ERROR_STOP=1 -f db/tests/privileges_test.sql
-- Everything runs inside a transaction that is rolled back, so the database is left empty.

\set ON_ERROR_STOP on
BEGIN;
\ir helpers.sql

-- auth_service: manages users and nothing else ---------------------------------
SET ROLE auth_service;

SELECT pg_temp.expect_ok('auth_service: create users (identity id)',
    $q$INSERT INTO accounts.users (email, password_hash, role) VALUES
           ('priv-rep@tally.test',  'hash', 'sales'),
           ('priv-cust@tally.test', 'hash', 'customer')$q$);
SELECT pg_temp.expect_ok('auth_service: read password hashes (for login)',
    $q$SELECT password_hash FROM accounts.users$q$);
SELECT pg_temp.expect_ok('auth_service: change a password',
    $q$UPDATE accounts.users SET password_hash = 'new-hash' WHERE email = 'priv-rep@tally.test'$q$);

SELECT pg_temp.expect_error('auth_service: cannot read products',
    $q$SELECT count(*) FROM inventory.products$q$, '42501');
SELECT pg_temp.expect_error('auth_service: cannot read customers',
    $q$SELECT count(*) FROM sales.customers$q$, '42501');
SELECT pg_temp.expect_error('auth_service: cannot read analytics',
    $q$SELECT count(*) FROM analytics.order_line_facts$q$, '42501');

RESET ROLE;

-- inventory_service: manages the catalog and stock ------------------------------
SET ROLE inventory_service;

SELECT pg_temp.expect_ok('inventory_service: add product',
    $q$INSERT INTO inventory.products (item_name, unit_price, sku) VALUES ('Widget', 10, 'PRIV-W')$q$);
SELECT pg_temp.expect_ok('inventory_service: add warehouse',
    $q$INSERT INTO inventory.warehouses (warehouse_name, location_code) VALUES ('Main', 'PRIV-LA')$q$);
SELECT pg_temp.expect_ok('inventory_service: add stock row',
    $q$INSERT INTO inventory.stock (item_id, warehouse_id, quantity, reorder_threshold)
       SELECT p.item_id, w.warehouse_id, 10, 2
         FROM inventory.products p, inventory.warehouses w
        WHERE p.sku = 'PRIV-W' AND w.location_code = 'PRIV-LA'$q$);
SELECT set_config('tally.movement_reason', 'receipt', true);
SELECT pg_temp.expect_ok('inventory_service: receive stock',
    $q$UPDATE inventory.stock SET quantity = quantity + 5$q$);
SELECT set_config('tally.movement_reason', '', true);
SELECT pg_temp.expect_ok('inventory_service: change price',
    $q$UPDATE inventory.products SET unit_price = 12 WHERE sku = 'PRIV-W'$q$);
SELECT pg_temp.expect_ok('inventory_service: change reorder threshold',
    $q$UPDATE inventory.stock SET reorder_threshold = 3$q$);
SELECT pg_temp.expect('inventory_service: its stock changes were recorded as movements',
    (SELECT array_agg(reason::text ORDER BY movement_id) FROM inventory.stock_movements)
    = ARRAY['initial', 'receipt']);
SELECT pg_temp.expect_ok('inventory_service: look up users without hashes',
    $q$SELECT user_id, email, role FROM accounts.users$q$);

SELECT pg_temp.expect_error('inventory_service: cannot read password hashes',
    $q$SELECT password_hash FROM accounts.users$q$, '42501');
SELECT pg_temp.expect_error('inventory_service: cannot write users',
    $q$INSERT INTO accounts.users (email, password_hash, role) VALUES ('x@tally.test', 'x', 'admin')$q$, '42501');
SELECT pg_temp.expect_error('inventory_service: cannot write movements directly',
    $q$INSERT INTO inventory.stock_movements (item_id, warehouse_id, quantity_change, quantity_after, reason)
       SELECT item_id, warehouse_id, 1, 1, 'adjustment' FROM inventory.stock$q$, '42501');
SELECT pg_temp.expect_error('inventory_service: cannot edit movement history',
    $q$UPDATE inventory.stock_movements SET quantity_after = 0$q$, '42501');
SELECT pg_temp.expect_error('inventory_service: cannot read orders',
    $q$SELECT count(*) FROM sales.orders$q$, '42501');
SELECT pg_temp.expect_error('inventory_service: cannot read customers',
    $q$SELECT count(*) FROM sales.customers$q$, '42501');
SELECT pg_temp.expect_error('inventory_service: cannot read analytics',
    $q$SELECT count(*) FROM analytics.low_stock$q$, '42501');

RESET ROLE;

-- sales_service: customers, orders, invoices; takes stock when placing orders ---
SET ROLE sales_service;

SELECT pg_temp.expect_ok('sales_service: create customer linked to users',
    $q$INSERT INTO sales.customers (customer_name, email, user_id, sales_rep_id)
       SELECT 'Acme', 'priv-acme@tally.test', cu.user_id, rep.user_id
         FROM accounts.users cu, accounts.users rep
        WHERE cu.email = 'priv-cust@tally.test' AND rep.email = 'priv-rep@tally.test'$q$);
SELECT pg_temp.expect_ok('sales_service: create order',
    $q$INSERT INTO sales.orders (customer_id, created_by, delivery_address)
       SELECT c.customer_id, c.sales_rep_id, '1 Main St'
         FROM sales.customers c WHERE c.email = 'priv-acme@tally.test'$q$);

-- Order placement as the transaction service does it: label the movement, lock, decrement,
-- write the line.
SELECT set_config('tally.movement_reason', 'sale', true),
       set_config('tally.order_id', (SELECT max(order_id) FROM sales.orders)::text, true);
SELECT pg_temp.expect_ok('sales_service: lock stock rows with FOR UPDATE',
    $q$SELECT quantity FROM inventory.stock s
         JOIN inventory.products p USING (item_id)
        WHERE p.sku = 'PRIV-W' FOR UPDATE OF s$q$);
SELECT pg_temp.expect_ok('sales_service: decrement stock quantity',
    $q$UPDATE inventory.stock s SET quantity = quantity - 4
         FROM inventory.products p
        WHERE p.item_id = s.item_id AND p.sku = 'PRIV-W'$q$);
SELECT set_config('tally.movement_reason', '', true), set_config('tally.order_id', '', true);
SELECT pg_temp.expect_ok('sales_service: add order line',
    $q$INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price)
       SELECT o.order_id, s.item_id, s.warehouse_id, 4, p.unit_price
         FROM sales.orders o
         JOIN sales.customers c     ON c.customer_id = o.customer_id
         JOIN inventory.stock s     ON true
         JOIN inventory.products p  ON p.item_id = s.item_id
        WHERE c.email = 'priv-acme@tally.test' AND p.sku = 'PRIV-W'$q$);
SELECT pg_temp.expect_ok('sales_service: issue invoice',
    $q$INSERT INTO sales.invoices (order_id, invoice_number, due_date, amount)
       SELECT order_id, 'PRIV-INV-1', '2026-12-31', 48 FROM sales.orders o
         JOIN sales.customers c USING (customer_id) WHERE c.email = 'priv-acme@tally.test'$q$);
SELECT pg_temp.expect_ok('sales_service: update order status',
    $q$UPDATE sales.orders SET status = 'invoiced'$q$);
SELECT pg_temp.expect('stock decremented and trigger still maintains last_update_at',
    (SELECT quantity = 11 AND last_update_at IS NOT NULL FROM inventory.stock s
       JOIN inventory.products p USING (item_id) WHERE p.sku = 'PRIV-W'));
SELECT pg_temp.expect('sales_service: sale recorded as a movement tied to the order',
    (SELECT (reason::text, quantity_change, order_id IS NOT NULL) = ('sale', -4, true)
       FROM inventory.stock_movements ORDER BY movement_id DESC LIMIT 1));
SELECT pg_temp.expect('sales_service: status changes recorded in history',
    (SELECT array_agg(to_status::text ORDER BY history_id) FROM sales.order_status_history)
    = ARRAY['pending', 'invoiced']);

SELECT pg_temp.expect_error('sales_service: cannot read password hashes',
    $q$SELECT password_hash FROM accounts.users$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot create users',
    $q$INSERT INTO accounts.users (email, password_hash, role) VALUES ('x@tally.test', 'x', 'admin')$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot change users',
    $q$UPDATE accounts.users SET role = 'admin'$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot edit status history',
    $q$UPDATE sales.order_status_history SET to_status = 'cancelled'$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot delete status history',
    $q$DELETE FROM sales.order_status_history$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot write movements directly',
    $q$DELETE FROM inventory.stock_movements$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot change reorder threshold',
    $q$UPDATE inventory.stock SET reorder_threshold = 0$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot add stock rows',
    $q$INSERT INTO inventory.stock (item_id, warehouse_id, quantity) VALUES (1, 1, 1)$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot delete stock rows',
    $q$DELETE FROM inventory.stock$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot add products',
    $q$INSERT INTO inventory.products (item_name, unit_price, sku) VALUES ('X', 1, 'PRIV-X')$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot change prices',
    $q$UPDATE inventory.products SET unit_price = 0$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot add warehouses',
    $q$INSERT INTO inventory.warehouses (warehouse_name, location_code) VALUES ('X', 'PRIV-X')$q$, '42501');
SELECT pg_temp.expect_error('sales_service: cannot read analytics',
    $q$SELECT count(*) FROM analytics.order_line_facts$q$, '42501');

RESET ROLE;

-- analytics_reader: reads the analytics views and nothing else -----------------
SET ROLE analytics_reader;

SELECT pg_temp.expect_ok('analytics_reader: read order_line_facts',     $q$SELECT * FROM analytics.order_line_facts$q$);
SELECT pg_temp.expect_ok('analytics_reader: read revenue_by_month',     $q$SELECT * FROM analytics.revenue_by_month$q$);
SELECT pg_temp.expect_ok('analytics_reader: read top_products',         $q$SELECT * FROM analytics.top_products$q$);
SELECT pg_temp.expect_ok('analytics_reader: read low_stock',            $q$SELECT * FROM analytics.low_stock$q$);
SELECT pg_temp.expect_ok('analytics_reader: read unpaid_invoices',      $q$SELECT * FROM analytics.unpaid_invoices$q$);
SELECT pg_temp.expect_ok('analytics_reader: read stock_movement_facts', $q$SELECT * FROM analytics.stock_movement_facts$q$);
SELECT pg_temp.expect_ok('analytics_reader: read daily_stock_levels',   $q$SELECT * FROM analytics.daily_stock_levels$q$);
SELECT pg_temp.expect_ok('analytics_reader: read order_status_changes', $q$SELECT * FROM analytics.order_status_changes$q$);
SELECT pg_temp.expect_ok('analytics_reader: read order_cycle_times',    $q$SELECT * FROM analytics.order_cycle_times$q$);
SELECT pg_temp.expect('analytics_reader: sees the order placed above',
    (SELECT count(*) FROM analytics.order_line_facts WHERE sku = 'PRIV-W') = 1);

SELECT pg_temp.expect_error('analytics_reader: cannot read users',
    $q$SELECT count(*) FROM accounts.users$q$, '42501');
SELECT pg_temp.expect_error('analytics_reader: cannot read orders directly',
    $q$SELECT count(*) FROM sales.orders$q$, '42501');
SELECT pg_temp.expect_error('analytics_reader: cannot read stock directly',
    $q$SELECT count(*) FROM inventory.stock$q$, '42501');
SELECT pg_temp.expect_error('analytics_reader: cannot create objects in analytics',
    $q$CREATE VIEW analytics.sneaky AS SELECT 1$q$, '42501');
SELECT pg_temp.expect_error('analytics_reader: cannot create objects in sales',
    $q$CREATE TABLE sales.sneaky (id int)$q$, '42501');

RESET ROLE;

ROLLBACK;
\echo 'All privilege tests passed.'
