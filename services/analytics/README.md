# Analytics service

Port **8004**. Owns schema **`analytics`** (read-only views). DB login: `tally_analytics`
(role `analytics_reader`). This login can read the views and nothing else.

All reports are `GET` endpoints for **admin** and **sales** users. Customers get 403, and
requests without a token get 401. Try them at http://localhost:8004/docs: log in at
http://localhost:8001/docs, then click **Authorize** and paste the token.

## Endpoints

| Endpoint | View | Filters |
|---|---|---|
| `/reports/summary` | several | none (headline numbers for a dashboard) |
| `/reports/revenue-by-month` | `revenue_by_month` | `start`, `end` |
| `/reports/top-products` | `order_line_facts` | `start`, `end`, `sort_by` (`revenue` \| `units`), `limit` ≤ 100 |
| `/reports/order-lines` | `order_line_facts` | `start`, `end`, `status`, `item_id`, `customer_id`, paging |
| `/reports/order-pipeline` | `order_cycle_times` | `start`, `end` |
| `/reports/order-cycle-times` | `order_cycle_times` | `start`, `end`, `status`, paging |
| `/reports/order-status-changes` | `order_status_changes` | `start`, `end`, `order_id`, paging |
| `/reports/unpaid-invoices` | `unpaid_invoices` | `overdue_only`, `customer_id` |
| `/reports/low-stock` | `low_stock` | `warehouse_id` |
| `/reports/stock-levels` | `daily_stock_levels` | `start`, `end` (default last 30 days, max 366), `item_id`, `warehouse_id` |
| `/reports/stock-movements` | `stock_movement_facts` | `start`, `end`, `item_id`, `warehouse_id`, `reason`, paging |

- **Dates** are `YYYY-MM-DD`, UTC, and inclusive. `start` after `end` returns 422.
- **Paging** uses `limit` (default 100, max 1000) and `offset`. Lists come back newest first.
- **Money** is a JSON string (`"79.92"`) so cents are never rounded. Convert it with
  `Number(...)` in a chart.
- **Revenue** counts only orders with status `confirmed` or `invoiced`.
- **`revenue-by-month`** returns zero rows for months without sales, so line charts have no gaps.

## Code layout

```
app/
  main.py               includes the three routers
  sales_reports.py      summary, revenue, top products, order lines
  order_reports.py      pipeline, cycle times, status changes, unpaid invoices
  inventory_reports.py  low stock, daily stock levels, stock movements
  schemas.py            response models (they define the /docs output)
  deps.py               staff-only check, date range and paging parameters, query helpers
tests/
  test_access.py        401/403/422 for every endpoint, no database needed
  test_reports.py       report values checked against db/local/seed.sql
```

**To add a report:**
1. Define the view in `db/ddl.sql` and add a test in `db/tests/analytics_test.sql`.
2. Add a response model in `schemas.py` and an endpoint in the matching router.
3. Add the path to the `REPORTS` list in `tests/test_access.py`. A test fails if you
   forget, so every endpoint stays covered by the access checks.

Keep queries on `analytics.*` views only. This service's login can't read the base tables.
Bind every value as a `:param`, and pass only the fixed strings written in code to `where(...)`.

**Testing:** `docker compose exec analytics pytest`. `test_reports.py` expects the
unmodified seed data. If you've added your own data, reset with
`docker compose down -v && docker compose up -d --build`.

## Tableau

Use Tableau's PostgreSQL connector and choose tables from the `analytics` schema.

- Local: `localhost:5432`, database `tally`, user `tally_analytics`, password `tally`.
- Supabase: the `tally_analytics` login and the pooler host, with SSL required.

Good data sources:
- **Sales:** `order_line_facts`, one row per line with every dimension already joined in.
- **Inventory over time:** `daily_stock_levels`, a continuous daily line per product and
  warehouse.
- **Fulfillment:** `order_cycle_times`.

**To do:** build the Tableau workbook.
