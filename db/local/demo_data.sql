-- LOCAL DOCKER ONLY. Never run on Supabase.
-- Demo data for building dashboards. load-demo.sh loads it into its own database
-- (tally_demo), so the tally database keeps exactly db/local/seed.sql, which the tests expect.
--
-- About six months of trading, ending when the script runs:
--   - orders grow over the period, with quieter weekends
--   - each order takes stock from a warehouse, and stock is restocked once it falls to
--     its reorder threshold, so inventory charts move up and down
--   - Sensor Module's restocks stop for the last three weeks, so it ends up low on stock
--   - about 6% of orders are cancelled the same evening and their stock is returned
--   - most orders are confirmed within hours and invoiced a few days later
--   - most invoices are paid; the rest stay unpaid, some of them overdue
--   - Gadget's price rises partway through, and Legacy Doohickey is discontinued
--
-- Every change goes through the normal tables, so the history triggers write
-- stock_movements and order_status_history as they would in production. Each new history
-- row is then backdated to the simulated time. The random seed is fixed, so every reload
-- produces nearly the same data, shifted to end on the day it is loaded.
--
-- Logins (password for all: password). Customers have no logins.
--   admin@tally.test         admin   user_id 1
--   rep.west@tally.test      sales   user_id 2
--   rep.east@tally.test      sales   user_id 3
--   rep.central@tally.test   sales   user_id 4
--   rep.south@tally.test     sales   user_id 5

BEGIN;

SELECT setseed(0.42);

-- Dimensions --------------------------------------------------------------------

INSERT INTO accounts.users (user_id, email, password_hash, role, created_at)
SELECT id, email,
       '$argon2id$v=19$m=65536,t=3,p=4$OdyoNwNi1tLLPi9EZBYEVQ$LjbIich+XsJoH6lZwdjAOVJWMayIODo0026Jiyo5YTc',
       role::accounts.user_role,
       now() - interval '240 days'
FROM (VALUES
    (1, 'admin@tally.test',       'admin'),
    (2, 'rep.west@tally.test',    'sales'),
    (3, 'rep.east@tally.test',    'sales'),
    (4, 'rep.central@tally.test', 'sales'),
    (5, 'rep.south@tally.test',   'sales')
) AS u (id, email, role);

-- weight: how often the product is ordered. max_qty: most units on one line.
CREATE TEMP TABLE demo_products ON COMMIT DROP AS
SELECT * FROM (VALUES
    ( 1, 'Widget',            9.99, 'WID-001', 5.0, 10, 25),
    ( 2, 'Gadget',           24.50, 'GAD-001', 4.0,  6, 15),
    ( 3, 'Sprocket',          3.25, 'SPR-001', 6.0, 20, 40),
    ( 4, 'Gizmo Pro',        89.00, 'GIZ-001', 2.0,  3,  5),
    ( 5, 'Bracket Kit',      14.75, 'BRK-001', 3.0,  8, 15),
    ( 6, 'Cable Pack',        7.50, 'CBL-001', 4.0, 12, 25),
    ( 7, 'Control Panel',   149.00, 'CTL-001', 1.0,  2,  3),
    ( 8, 'Sensor Module',    39.90, 'SEN-001', 2.0,  4,  6),
    ( 9, 'Mounting Plate',   12.00, 'MNT-001', 3.0,  8, 12),
    (10, 'Legacy Doohickey',  4.00, 'OLD-001', 2.0, 10, 10)
) AS p (item_id, item_name, unit_price, sku, weight, max_qty, reorder_threshold);

INSERT INTO inventory.products (item_id, item_name, unit_price, sku, created_at, updated_at)
SELECT item_id, item_name, unit_price, sku, now() - interval '240 days', now() - interval '240 days'
FROM demo_products;

INSERT INTO inventory.warehouses (warehouse_id, warehouse_name, location_code) VALUES
    (1, 'Los Angeles', 'LA-01'),
    (2, 'New York',    'NY-01'),
    (3, 'Chicago',     'CHI-01');

-- Every product in Los Angeles and New York; odd-numbered products in Chicago too.
-- Smaller warehouses get lower thresholds.
INSERT INTO inventory.stock (item_id, warehouse_id, quantity, reorder_threshold)
SELECT p.item_id, w.warehouse_id,
       t.threshold * 4 + floor(random() * t.threshold)::int,
       t.threshold
FROM demo_products p
CROSS JOIN inventory.warehouses w
CROSS JOIN LATERAL (
    SELECT greatest(1, round(p.reorder_threshold
        * CASE w.warehouse_id WHEN 1 THEN 1.0 WHEN 2 THEN 0.8 ELSE 0.5 END))::int AS threshold
) t
WHERE w.warehouse_id IN (1, 2) OR p.item_id % 2 = 1
ORDER BY p.item_id, w.warehouse_id;

-- The opening stock movements belong at the start of the simulated period.
UPDATE inventory.stock_movements
SET created_at = ((current_date - 182) + time '00:00') AT TIME ZONE 'UTC'
WHERE reason = 'initial';

-- weight: how often the customer orders. active_from: day index of their first possible order.
CREATE TEMP TABLE demo_customers ON COMMIT DROP AS
SELECT * FROM (VALUES
    ( 1, 'Acme Corp',            'orders@acme.test',          2, 5.0,   0, '1 Acme Way, Los Angeles, CA'),
    ( 2, 'Bluebird Supply',      'orders@bluebird.test',      3, 3.0,   0, '22 Wren St, Brooklyn, NY'),
    ( 3, 'Cedar Hardware',       'orders@cedarhw.test',       4, 2.5,   0, '310 Cedar Ave, Chicago, IL'),
    ( 4, 'Delta Fabrication',    'orders@deltafab.test',      5, 2.0,   0, '48 Delta Rd, Houston, TX'),
    ( 5, 'Evergreen Builders',   'orders@evergreen.test',     2, 2.0,   0, '9 Pine Ct, Portland, OR'),
    ( 6, 'Foxglove Interiors',   'orders@foxglove.test',      3, 1.5,   0, '75 Bloom Ln, Boston, MA'),
    ( 7, 'Granite Works',        'orders@granite.test',       4, 1.5,   0, '600 Quarry Dr, Denver, CO'),
    ( 8, 'Harbor Marine',        'orders@harbor.test',        5, 1.0,   0, '3 Dock St, Miami, FL'),
    ( 9, 'Ironwood Tools',       'orders@ironwood.test',      4, 1.0,   0, '17 Forge Blvd, Detroit, MI'),
    (10, 'Juniper Labs',         'orders@juniper.test',       2, 1.0,   0, '200 Lab Pkwy, San Jose, CA'),
    (11, 'Keystone Electric',    'orders@keystone.test',      3, 1.0,   0, '88 Volt Ave, Philadelphia, PA'),
    (12, 'Lakeside Outfitters',  'orders@lakeside.test',      4, 0.8,   0, '5 Shore Rd, Milwaukee, WI'),
    (13, 'Maple Street Makers',  'orders@maplestreet.test',   5, 2.0,  60, '140 Maple St, Atlanta, GA'),
    (14, 'Northwind Repair',     'orders@northwind.test',     3, 2.5, 110, '61 Gale Way, Newark, NJ'),
    (15, 'Orchard Robotics',     'orders@orchard.test',       2, 3.0, 150, '400 Orchard Loop, Sacramento, CA')
) AS c (customer_id, customer_name, email, sales_rep_id, weight, active_from, address);

INSERT INTO sales.customers (customer_id, customer_name, email, sales_rep_id, created_at, updated_at)
SELECT customer_id, customer_name, email, sales_rep_id,
       ((current_date - 182 + active_from) + time '09:00') AT TIME ZONE 'UTC' - interval '3 days',
       ((current_date - 182 + active_from) + time '09:00') AT TIME ZONE 'UTC' - interval '3 days'
FROM demo_customers;

-- Six months of trading ------------------------------------------------------------

DO $$
DECLARE
    n_days          constant int := 182;
    start_day       constant date := current_date - n_days;
    discontinue_at  constant int := 100;  -- day index when Legacy Doohickey stops selling
    price_rise_at   constant int := 120;  -- day index when Gadget's price rises
    day_idx         int;
    d               date;
    n_orders        int;
    rate            float8;
    ts              timestamptz;
    confirm_ts      timestamptz;
    invoice_ts      timestamptz;
    paid_ts         timestamptz;
    cancel_ts       timestamptz;
    cust            record;
    pick            record;
    st              record;
    v_order         int;
    wh              int;
    q               int;
    items           int[];
    whs             int[];
    qtys            int[];
    cancels         int[];
    k               int;
BEGIN
    FOR day_idx IN 0..n_days LOOP
        d := start_day + day_idx;

        IF day_idx = price_rise_at THEN
            UPDATE inventory.products SET unit_price = 25.95 WHERE item_id = 2;
        END IF;

        -- Morning deliveries: rows at or below threshold have a 30% chance of a restock each
        -- day. Sensor Module's supplier stops delivering for the last three weeks, so it
        -- runs low and shows up in analytics.low_stock.
        ts := (d + time '06:00') AT TIME ZONE 'UTC';
        IF ts < now() THEN
            PERFORM set_config('tally.user_id', '1', true),
                    set_config('tally.movement_reason', 'receipt', true),
                    set_config('tally.order_id', '', true);
            FOR st IN
                SELECT s.item_id, s.warehouse_id, s.reorder_threshold
                FROM inventory.stock s
                WHERE s.quantity <= s.reorder_threshold
                  AND (s.item_id <> 10 OR day_idx < discontinue_at)
                  AND (s.item_id <> 8  OR day_idx < n_days - 21)
                ORDER BY s.item_id, s.warehouse_id
            LOOP
                IF random() < 0.30 THEN
                    UPDATE inventory.stock
                    SET quantity = st.reorder_threshold * 4 + floor(random() * st.reorder_threshold)::int
                    WHERE item_id = st.item_id AND warehouse_id = st.warehouse_id;
                    UPDATE inventory.stock_movements SET created_at = ts
                    WHERE movement_id = (SELECT max(movement_id) FROM inventory.stock_movements);
                END IF;
            END LOOP;
        END IF;

        -- Orders between 08:00 and 18:00 UTC, growing over the period, fewer at weekends.
        rate := 1.2 + 2.8 * day_idx / n_days;
        IF extract(isodow FROM d) IN (6, 7) THEN
            rate := rate * 0.35;
        END IF;
        n_orders := floor(rate * 0.5 + random() * rate + random())::int;
        cancels := '{}';

        FOR ts IN
            SELECT (d + time '08:00' + random() * interval '10 hours') AT TIME ZONE 'UTC'
            FROM generate_series(1, n_orders)
            ORDER BY 1
        LOOP
            EXIT WHEN ts >= now();

            SELECT * INTO cust FROM demo_customers c
            WHERE c.active_from <= day_idx
            ORDER BY -ln(1 - random()) / c.weight
            LIMIT 1;

            -- Choose one to three different products, each from a warehouse that has enough.
            items := '{}'; whs := '{}'; qtys := '{}';
            FOR k IN 1..(1 + floor(random() * 3))::int LOOP
                SELECT p.item_id, p.max_qty INTO pick FROM demo_products p
                WHERE p.item_id <> ALL (items)
                  AND (p.item_id <> 10 OR day_idx < discontinue_at)
                ORDER BY -ln(1 - random()) / p.weight
                LIMIT 1;
                q := 1 + floor(random() * pick.max_qty)::int;
                SELECT s.warehouse_id INTO wh FROM inventory.stock s
                WHERE s.item_id = pick.item_id AND s.quantity >= q
                ORDER BY random()
                LIMIT 1;
                CONTINUE WHEN wh IS NULL;  -- out of stock everywhere: drop this line
                items := items || pick.item_id;
                whs := whs || wh;
                qtys := qtys || q;
            END LOOP;
            CONTINUE WHEN cardinality(items) = 0;

            -- Place the order the way the transactions service does.
            PERFORM set_config('tally.user_id', cust.sales_rep_id::text, true),
                    set_config('tally.movement_reason', '', true),
                    set_config('tally.order_id', '', true);
            INSERT INTO sales.orders (customer_id, created_by, order_date, delivery_address)
            VALUES (cust.customer_id, cust.sales_rep_id, ts, cust.address)
            RETURNING order_id INTO v_order;
            UPDATE sales.order_status_history SET changed_at = ts
            WHERE history_id = (SELECT max(history_id) FROM sales.order_status_history);

            PERFORM set_config('tally.movement_reason', 'sale', true),
                    set_config('tally.order_id', v_order::text, true);
            FOR k IN 1..cardinality(items) LOOP
                UPDATE inventory.stock SET quantity = quantity - qtys[k]
                WHERE item_id = items[k] AND warehouse_id = whs[k];
                UPDATE inventory.stock_movements SET created_at = ts
                WHERE movement_id = (SELECT max(movement_id) FROM inventory.stock_movements);
                INSERT INTO sales.order_lines (order_id, item_id, warehouse_id, quantity, unit_price)
                SELECT v_order, items[k], whs[k], qtys[k], p.unit_price
                FROM inventory.products p WHERE p.item_id = items[k];
            END LOOP;

            IF random() < 0.06 THEN
                cancels := cancels || v_order;  -- cancelled this evening, after the day's orders
                CONTINUE;
            END IF;

            -- Confirmed usually within a few hours, occasionally after a day or more.
            confirm_ts := ts + (0.5 + 36 * random() * random()) * interval '1 hour';
            CONTINUE WHEN confirm_ts >= now();
            UPDATE sales.orders SET status = 'confirmed' WHERE order_id = v_order;
            UPDATE sales.order_status_history SET changed_at = confirm_ts
            WHERE history_id = (SELECT max(history_id) FROM sales.order_status_history);

            invoice_ts := confirm_ts + (12 + 96 * random()) * interval '1 hour';
            CONTINUE WHEN invoice_ts >= now();
            UPDATE sales.orders SET status = 'invoiced' WHERE order_id = v_order;
            UPDATE sales.order_status_history SET changed_at = invoice_ts
            WHERE history_id = (SELECT max(history_id) FROM sales.order_status_history);

            -- 30-day terms. Most are paid, a few after the due date; the rest stay unpaid.
            paid_ts := invoice_ts + (3 + 40 * random()) * interval '1 day';
            INSERT INTO sales.invoices (order_id, invoice_number, issue_date, due_date, amount, status, paid_at)
            SELECT v_order,
                   'INV-' || lpad(v_order::text, 5, '0'),
                   invoice_ts,
                   (invoice_ts AT TIME ZONE 'UTC')::date + 30,
                   sum(l.quantity * l.unit_price),
                   CASE WHEN random() < 0.95 AND paid_ts < now()
                        THEN 'paid' ELSE 'unpaid' END::sales.invoice_status,
                   NULL
            FROM sales.order_lines l WHERE l.order_id = v_order;
            UPDATE sales.invoices SET paid_at = paid_ts
            WHERE order_id = v_order AND status = 'paid';
        END LOOP;

        -- Evening cancellations return the units to the warehouses they came from.
        FOREACH v_order IN ARRAY cancels LOOP
            cancel_ts := (d + time '20:00' + random() * interval '2 hours') AT TIME ZONE 'UTC';
            CONTINUE WHEN cancel_ts >= now();  -- tonight's cancellations stay pending for now
            PERFORM set_config('tally.user_id', created_by::text, true),
                    set_config('tally.movement_reason', 'sale_cancelled', true),
                    set_config('tally.order_id', v_order::text, true)
            FROM sales.orders WHERE order_id = v_order;
            FOR st IN SELECT item_id, warehouse_id, quantity FROM sales.order_lines
                      WHERE order_id = v_order ORDER BY line_id
            LOOP
                UPDATE inventory.stock SET quantity = quantity + st.quantity
                WHERE item_id = st.item_id AND warehouse_id = st.warehouse_id;
                UPDATE inventory.stock_movements SET created_at = cancel_ts
                WHERE movement_id = (SELECT max(movement_id) FROM inventory.stock_movements);
            END LOOP;
            UPDATE sales.orders SET status = 'cancelled' WHERE order_id = v_order;
            UPDATE sales.order_status_history SET changed_at = cancel_ts
            WHERE history_id = (SELECT max(history_id) FROM sales.order_status_history);
        END LOOP;
    END LOOP;
END;
$$;

UPDATE inventory.products SET is_active = false WHERE item_id = 10;

-- The updated_at triggers stamped rows with the load time. Set them to the simulated time.
ALTER TABLE sales.orders DISABLE TRIGGER trg_orders_updated_at;
ALTER TABLE inventory.stock DISABLE TRIGGER trg_stock_last_update_at;

UPDATE sales.orders o SET updated_at = h.last_change
FROM (SELECT order_id, max(changed_at) AS last_change
      FROM sales.order_status_history GROUP BY order_id) h
WHERE h.order_id = o.order_id;

UPDATE inventory.stock s SET last_update_at = m.last_change
FROM (SELECT item_id, warehouse_id, max(created_at) AS last_change
      FROM inventory.stock_movements GROUP BY item_id, warehouse_id) m
WHERE m.item_id = s.item_id AND m.warehouse_id = s.warehouse_id;

ALTER TABLE sales.orders ENABLE TRIGGER trg_orders_updated_at;
ALTER TABLE inventory.stock ENABLE TRIGGER trg_stock_last_update_at;

-- Dimension rows used explicit ids; move the identity counters past them.
SELECT setval(pg_get_serial_sequence('accounts.users',       'user_id'),      100);
SELECT setval(pg_get_serial_sequence('inventory.products',   'item_id'),      100);
SELECT setval(pg_get_serial_sequence('inventory.warehouses', 'warehouse_id'), 100);
SELECT setval(pg_get_serial_sequence('sales.customers',      'customer_id'),  100);

COMMIT;
