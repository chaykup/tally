-- Constraint tests for db/ddl.sql. Run against a database where ddl.sql has already been loaded:
--   psql -v ON_ERROR_STOP=1 -f db/tests/constraints_test.sql
-- Any failed assertion raises an exception, which makes psql exit non-zero and fails CI.
-- Everything runs inside a transaction that is rolled back, so the database is left empty.

\set ON_ERROR_STOP on
BEGIN;

-- expect_error(statement, sqlstate): passes only if the statement fails with exactly that error.
--   23502 not_null_violation   23503 foreign_key_violation
--   23505 unique_violation     23514 check_violation   22P02 invalid_text_representation (bad enum)
CREATE FUNCTION pg_temp.expect_error(label text, stmt text, expected_state text) RETURNS void AS $$
BEGIN
    EXECUTE stmt;
    RAISE EXCEPTION 'FAIL [%]: statement succeeded but should have raised %', label, expected_state;
EXCEPTION
    WHEN OTHERS THEN
        IF SQLSTATE = 'P0001' AND SQLERRM LIKE 'FAIL [%' THEN
            RAISE;  -- re-raise our own "should have failed" error
        ELSIF SQLSTATE <> expected_state THEN
            RAISE EXCEPTION 'FAIL [%]: expected SQLSTATE %, got % (%)', label, expected_state, SQLSTATE, SQLERRM;
        END IF;
        RAISE NOTICE 'ok   %', label;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION pg_temp.expect(label text, condition boolean) RETURNS void AS $$
BEGIN
    IF condition IS NOT TRUE THEN
        RAISE EXCEPTION 'FAIL [%]', label;
    END IF;
    RAISE NOTICE 'ok   %', label;
END;
$$ LANGUAGE plpgsql;

-- Fixtures: valid data in every table (also proves the happy path works) ------

INSERT INTO users (user_id, email, password_hash, role) VALUES
    (1, 'admin@tally.test', 'x', 'admin'),
    (2, 'rep@tally.test',   'x', 'sales'),
    (3, 'cust@tally.test',  'x', 'customer');
INSERT INTO products (item_id, item_name, unit_price, sku) VALUES (1, 'Widget', 9.99, 'W-1');
INSERT INTO warehouses (warehouse_id, warehouse_name, location_code) VALUES
    (1, 'Main', 'LA-01'),
    (2, 'East', 'NY-01');
INSERT INTO stock (item_id, warehouse_id, quantity, reorder_threshold) VALUES (1, 1, 5, 2);
INSERT INTO customers (customer_id, customer_name, email, user_id, sales_rep_id)
    VALUES (1, 'Acme', 'acme@tally.test', 3, 2);
INSERT INTO orders (order_id, customer_id, created_by, delivery_address) VALUES (1, 1, 2, '1 Main St');
INSERT INTO order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 2, 9.99);
INSERT INTO invoices (order_id, invoice_number, due_date, amount) VALUES (1, 'INV-0001', '2026-12-31', 19.98);

-- Fixtures used explicit IDs, so move identity counters past them. Otherwise a later insert
-- could collide on the primary key and "pass" a unique test for the wrong reason.
SELECT setval(pg_get_serial_sequence('users',      'user_id'),      1000);
SELECT setval(pg_get_serial_sequence('products',   'item_id'),      1000);
SELECT setval(pg_get_serial_sequence('warehouses', 'warehouse_id'), 1000);
SELECT setval(pg_get_serial_sequence('customers',  'customer_id'),  1000);
SELECT setval(pg_get_serial_sequence('orders',     'order_id'),     1000);

SELECT pg_temp.expect('fixtures inserted', (SELECT count(*) FROM invoices) = 1);
SELECT pg_temp.expect('order status defaults to pending',
    (SELECT status FROM orders WHERE order_id = 1) = 'pending');

-- users ------------------------------------------------------------------------
SELECT pg_temp.expect_error('users: duplicate email',
    $q$INSERT INTO users (email, password_hash, role) VALUES ('rep@tally.test', 'x', 'sales')$q$, '23505');
SELECT pg_temp.expect_error('users: invalid role',
    $q$INSERT INTO users (email, password_hash, role) VALUES ('new@tally.test', 'x', 'manager')$q$, '22P02');
SELECT pg_temp.expect_error('users: missing password_hash',
    $q$INSERT INTO users (email, role) VALUES ('new@tally.test', 'sales')$q$, '23502');

-- products ---------------------------------------------------------------------
SELECT pg_temp.expect_error('products: duplicate sku',
    $q$INSERT INTO products (item_name, unit_price, sku) VALUES ('Copy', 1, 'W-1')$q$, '23505');
SELECT pg_temp.expect_error('products: negative price',
    $q$INSERT INTO products (item_name, unit_price, sku) VALUES ('Bad', -1, 'B-1')$q$, '23514');
SELECT pg_temp.expect_error('products: hard delete blocked while referenced',
    $q$DELETE FROM products WHERE item_id = 1$q$, '23503');

-- warehouses -------------------------------------------------------------------
SELECT pg_temp.expect_error('warehouses: duplicate location_code',
    $q$INSERT INTO warehouses (warehouse_name, location_code) VALUES ('Dup', 'LA-01')$q$, '23505');

-- stock ------------------------------------------------------------------------
SELECT pg_temp.expect_error('stock: quantity cannot go negative (oversell guard)',
    $q$UPDATE stock SET quantity = quantity - 6 WHERE item_id = 1 AND warehouse_id = 1$q$, '23514');
SELECT pg_temp.expect_error('stock: negative reorder_threshold',
    $q$UPDATE stock SET reorder_threshold = -1 WHERE item_id = 1$q$, '23514');
SELECT pg_temp.expect_error('stock: duplicate product+warehouse row',
    $q$INSERT INTO stock (item_id, warehouse_id, quantity) VALUES (1, 1, 3)$q$, '23505');
SELECT pg_temp.expect_error('stock: unknown product',
    $q$INSERT INTO stock (item_id, warehouse_id, quantity) VALUES (999, 1, 3)$q$, '23503');
SELECT pg_temp.expect_error('stock: unknown warehouse',
    $q$INSERT INTO stock (item_id, warehouse_id, quantity) VALUES (1, 999, 3)$q$, '23503');

-- customers --------------------------------------------------------------------
SELECT pg_temp.expect_error('customers: duplicate email',
    $q$INSERT INTO customers (customer_name, email, sales_rep_id) VALUES ('X', 'acme@tally.test', 2)$q$, '23505');
SELECT pg_temp.expect_error('customers: one login per customer',
    $q$INSERT INTO customers (customer_name, email, user_id, sales_rep_id) VALUES ('X', 'x@tally.test', 3, 2)$q$, '23505');
SELECT pg_temp.expect_error('customers: sales rep required',
    $q$INSERT INTO customers (customer_name, email) VALUES ('X', 'x@tally.test')$q$, '23502');
SELECT pg_temp.expect_error('customers: unknown sales rep',
    $q$INSERT INTO customers (customer_name, email, sales_rep_id) VALUES ('X', 'x@tally.test', 999)$q$, '23503');

-- orders -----------------------------------------------------------------------
SELECT pg_temp.expect_error('orders: unknown customer',
    $q$INSERT INTO orders (customer_id, created_by, delivery_address) VALUES (999, 2, 'a')$q$, '23503');
SELECT pg_temp.expect_error('orders: unknown creator',
    $q$INSERT INTO orders (customer_id, created_by, delivery_address) VALUES (1, 999, 'a')$q$, '23503');
SELECT pg_temp.expect_error('orders: invalid status',
    $q$UPDATE orders SET status = 'shipped' WHERE order_id = 1$q$, '22P02');

-- order_lines ------------------------------------------------------------------
SELECT pg_temp.expect_error('order_lines: quantity must be positive',
    $q$INSERT INTO order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 0, 9.99)$q$, '23514');
SELECT pg_temp.expect_error('order_lines: negative price',
    $q$UPDATE order_lines SET unit_price = -1 WHERE order_id = 1$q$, '23514');
SELECT pg_temp.expect_error('order_lines: duplicate product+warehouse on one order',
    $q$INSERT INTO order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 1, 1, 9.99)$q$, '23505');
SELECT pg_temp.expect_error('order_lines: warehouse must stock the product',
    $q$INSERT INTO order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES (1, 1, 2, 1, 9.99)$q$, '23503');

-- invoices ---------------------------------------------------------------------
SELECT pg_temp.expect_error('invoices: one invoice per order',
    $q$INSERT INTO invoices (order_id, invoice_number, due_date, amount) VALUES (1, 'INV-0002', '2026-12-31', 1)$q$, '23505');
SELECT pg_temp.expect_error('invoices: negative amount',
    $q$UPDATE invoices SET amount = -1 WHERE order_id = 1$q$, '23514');
SELECT pg_temp.expect_error('invoices: invalid status',
    $q$UPDATE invoices SET status = 'refunded' WHERE order_id = 1$q$, '22P02');
SELECT pg_temp.expect_error('orders: delete blocked while invoiced',
    $q$DELETE FROM orders WHERE order_id = 1$q$, '23503');

-- triggers ---------------------------------------------------------------------
UPDATE products SET updated_at = '2000-01-01' WHERE item_id = 1;  -- trigger overwrites this
SELECT pg_temp.expect('products.updated_at maintained by trigger',
    (SELECT updated_at > '2000-01-01' FROM products WHERE item_id = 1));
UPDATE stock SET last_update_at = '2000-01-01' WHERE item_id = 1;
SELECT pg_temp.expect('stock.last_update_at maintained by trigger',
    (SELECT last_update_at > '2000-01-01' FROM stock WHERE item_id = 1));

-- cascade ----------------------------------------------------------------------
DELETE FROM invoices WHERE order_id = 1;
DELETE FROM orders WHERE order_id = 1;
SELECT pg_temp.expect('deleting an order cascades to its lines',
    (SELECT count(*) FROM order_lines WHERE order_id = 1) = 0);

ROLLBACK;
\echo 'All constraint tests passed.'
