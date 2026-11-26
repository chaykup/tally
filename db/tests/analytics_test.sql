-- Analytics view tests: known fixtures in, known report numbers out.
-- Run against a database where ddl.sql has already been loaded:
--   psql -v ON_ERROR_STOP=1 -f db/tests/analytics_test.sql
-- Everything runs inside a transaction that is rolled back, so the database is left empty.

\set ON_ERROR_STOP on
BEGIN;
\ir helpers.sql

-- Fixtures ---------------------------------------------------------------------
-- Product A sells for 10, B for 5. C is discontinued (inactive) and out of stock.
INSERT INTO accounts.users (user_id, email, password_hash, role) VALUES
    (1, 'rep@tally.test',  'x', 'sales'),
    (2, 'cust@tally.test', 'x', 'customer');
INSERT INTO inventory.products (item_id, item_name, unit_price, sku, is_active) VALUES
    (1, 'Alpha',   10, 'A', true),
    (2, 'Bravo',    5, 'B', true),
    (3, 'Charlie',  1, 'C', false);
INSERT INTO inventory.warehouses (warehouse_id, warehouse_name, location_code) VALUES (1, 'Main', 'LA-01');
INSERT INTO inventory.stock (item_id, warehouse_id, quantity, reorder_threshold) VALUES
    (1, 1,   3,  5),   -- low: 2 short
    (2, 1, 100, 10),   -- fine
    (3, 1,   0,  5);   -- low, but product is inactive, so not reported
INSERT INTO sales.customers (customer_id, customer_name, email, user_id, sales_rep_id)
    VALUES (1, 'Acme', 'acme@tally.test', 2, 1);

INSERT INTO sales.orders (order_id, customer_id, created_by, delivery_address, order_date, status) VALUES
    (1, 1, 1, 'a', '2026-01-15 12:00Z',     'invoiced'),
    (2, 1, 1, 'a', '2026-01-20 12:00Z',     'invoiced'),
    (3, 1, 1, 'a', '2026-02-10 12:00Z',     'pending'),    -- not revenue yet
    (4, 1, 1, 'a', '2026-02-11 12:00Z',     'cancelled'),  -- never revenue
    (5, 1, 1, 'a', '2026-02-28 23:30-08',   'pending');    -- 2026-03-01 07:30 in UTC; confirmed below
INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price) VALUES
    (1, 1, 1,  2, 10),  -- 20
    (1, 2, 1,  4,  5),  -- 20
    (2, 1, 1,  1, 10),  -- 10
    (3, 1, 1,  5, 10),
    (4, 2, 1, 10,  5),
    (5, 2, 1,  2,  5);  -- 10
INSERT INTO sales.invoices (order_id, invoice_number, due_date, amount, status, paid_at) VALUES
    (1, 'INV-1', '2026-02-15', 40, 'paid', '2026-02-01'),
    (2, 'INV-2', '2000-01-01', 10, 'unpaid', NULL);        -- long overdue

UPDATE sales.orders SET status = 'confirmed' WHERE order_id = 5;

-- History rows are stamped with now(), which is the same instant for the whole test
-- transaction. Backdate them to build a realistic timeline.
-- Stock: every row starts on 2026-01-01. Bravo then gets a receipt and a sale on 2026-01-03.
UPDATE inventory.stock_movements SET created_at = '2026-01-01 08:00Z';
SELECT set_config('tally.movement_reason', 'receipt', true);
UPDATE inventory.stock SET quantity = quantity + 20 WHERE item_id = 2;   -- 100 -> 120
UPDATE inventory.stock_movements SET created_at = '2026-01-03 10:00Z' WHERE reason = 'receipt';
SELECT set_config('tally.movement_reason', 'sale', true), set_config('tally.order_id', '1', true);
UPDATE inventory.stock SET quantity = quantity - 15 WHERE item_id = 2;   -- 120 -> 105
UPDATE inventory.stock_movements SET created_at = '2026-01-03 18:00Z' WHERE reason = 'sale';
SELECT set_config('tally.movement_reason', '', true), set_config('tally.order_id', '', true);

-- Orders: order 5 was created pending at its order_date and confirmed 6 hours later.
UPDATE sales.order_status_history SET changed_at = '2026-03-01 07:30Z' WHERE order_id = 5 AND to_status = 'pending';
UPDATE sales.order_status_history SET changed_at = '2026-03-01 13:30Z' WHERE order_id = 5 AND to_status = 'confirmed';

-- Assertions run as the analytics role, the same access Tableau will have.
SET ROLE analytics_reader;

-- order_line_facts -------------------------------------------------------------
SELECT pg_temp.expect('facts: one row per order line',
    (SELECT count(*) FROM analytics.order_line_facts) = 6);
SELECT pg_temp.expect('facts: only confirmed/invoiced lines count as revenue',
    (SELECT count(*) FROM analytics.order_line_facts WHERE counts_as_revenue) = 4);
SELECT pg_temp.expect('facts: line_total = quantity * unit_price',
    (SELECT line_total FROM analytics.order_line_facts WHERE order_id = 4) = 50);
SELECT pg_temp.expect('facts: rep and status come through as plain values',
    (SELECT sales_rep_email = 'rep@tally.test' AND order_status = 'cancelled'
       FROM analytics.order_line_facts WHERE order_id = 4));
SELECT pg_temp.expect('facts: order day is bucketed in UTC',
    (SELECT order_day_utc FROM analytics.order_line_facts WHERE order_id = 5) = '2026-03-01');

-- revenue_by_month -------------------------------------------------------------
SELECT pg_temp.expect('revenue: January = 2 orders, 7 units, 50.00',
    (SELECT (order_count, units_sold, revenue) = (2::bigint, 7::bigint, 50.00::numeric)
       FROM analytics.revenue_by_month WHERE month = '2026-01-01'));
SELECT pg_temp.expect('revenue: February has only pending/cancelled orders, so no row',
    NOT EXISTS (SELECT 1 FROM analytics.revenue_by_month WHERE month = '2026-02-01'));
SELECT pg_temp.expect('revenue: March = 1 order, 10.00 (UTC bucketing)',
    (SELECT (order_count, revenue) = (1::bigint, 10.00::numeric)
       FROM analytics.revenue_by_month WHERE month = '2026-03-01'));

-- top_products -----------------------------------------------------------------
SELECT pg_temp.expect('top products: Alpha = 2 orders, 3 units, 30.00',
    (SELECT (order_count, units_sold, revenue) = (2::bigint, 3::bigint, 30.00::numeric)
       FROM analytics.top_products WHERE sku = 'A'));
SELECT pg_temp.expect('top products: Bravo = 2 orders, 6 units, 30.00 (cancelled order excluded)',
    (SELECT (order_count, units_sold, revenue) = (2::bigint, 6::bigint, 30.00::numeric)
       FROM analytics.top_products WHERE sku = 'B'));
SELECT pg_temp.expect('top products: unsold products are not listed',
    NOT EXISTS (SELECT 1 FROM analytics.top_products WHERE sku = 'C'));

-- low_stock --------------------------------------------------------------------
SELECT pg_temp.expect('low stock: only the active product under its threshold',
    (SELECT array_agg(sku) FROM analytics.low_stock) = ARRAY['A']::varchar[]);
SELECT pg_temp.expect('low stock: shortfall = threshold - quantity',
    (SELECT shortfall FROM analytics.low_stock WHERE sku = 'A') = 2);

-- unpaid_invoices --------------------------------------------------------------
SELECT pg_temp.expect('unpaid invoices: paid invoices are excluded',
    (SELECT array_agg(invoice_number) FROM analytics.unpaid_invoices) = ARRAY['INV-2']::varchar[]);
SELECT pg_temp.expect('unpaid invoices: overdue flag and days overdue',
    (SELECT is_overdue AND days_overdue = current_date - DATE '2000-01-01'
       FROM analytics.unpaid_invoices WHERE invoice_number = 'INV-2'));

-- stock_movement_facts ---------------------------------------------------------
SELECT pg_temp.expect('movements: Bravo history is initial, receipt, sale with levels',
    (SELECT array_agg(reason || ' ' || quantity_change || ' -> ' || quantity_after ORDER BY movement_id)
       FROM analytics.stock_movement_facts WHERE sku = 'B')
    = ARRAY['initial 100 -> 100', 'receipt 20 -> 120', 'sale -15 -> 105']);

-- daily_stock_levels -----------------------------------------------------------
SELECT pg_temp.expect('daily levels: Jan 1 closes at the initial level',
    (SELECT closing_quantity FROM analytics.daily_stock_levels WHERE sku = 'B' AND day = '2026-01-01') = 100);
SELECT pg_temp.expect('daily levels: a day without movements carries the level forward',
    (SELECT closing_quantity FROM analytics.daily_stock_levels WHERE sku = 'B' AND day = '2026-01-02') = 100);
SELECT pg_temp.expect('daily levels: a day with several movements closes at the last one',
    (SELECT closing_quantity FROM analytics.daily_stock_levels WHERE sku = 'B' AND day = '2026-01-03') = 105);
SELECT pg_temp.expect('daily levels: one row per day from the first movement through today',
    (SELECT count(*) = (current_date - DATE '2026-01-01') + 1
            AND max(day) = (now() AT TIME ZONE 'UTC')::date
       FROM analytics.daily_stock_levels WHERE sku = 'B'));
SELECT pg_temp.expect('daily levels: today matches current stock',
    (SELECT closing_quantity FROM analytics.daily_stock_levels
      WHERE sku = 'B' AND day = (now() AT TIME ZONE 'UTC')::date) = 105);
SELECT pg_temp.expect('daily levels: flags days at or below the reorder threshold',
    (SELECT bool_and(at_or_below_threshold) FROM analytics.daily_stock_levels WHERE sku = 'A')
    AND NOT (SELECT bool_or(at_or_below_threshold) FROM analytics.daily_stock_levels WHERE sku = 'B'));

-- order_status_changes / order_cycle_times -------------------------------------
SELECT pg_temp.expect('status changes: order 5 went pending then confirmed',
    (SELECT array_agg(coalesce(from_status, 'new') || '->' || to_status ORDER BY changed_at)
       FROM analytics.order_status_changes WHERE order_id = 5)
    = ARRAY['new->pending', 'pending->confirmed']);
SELECT pg_temp.expect('cycle times: order 5 took 6 hours to confirm',
    (SELECT hours_to_confirm FROM analytics.order_cycle_times WHERE order_id = 5) = 6);
SELECT pg_temp.expect('cycle times: one row per order, unconfirmed orders have no confirm time',
    (SELECT count(*) FROM analytics.order_cycle_times) = 5
    AND (SELECT confirmed_at IS NULL AND current_status = 'pending' FROM analytics.order_cycle_times WHERE order_id = 3));

RESET ROLE;

ROLLBACK;
\echo 'All analytics tests passed.'
