# Analytics service

Port **8004**. Owns schema **`analytics`** (read-only views). DB login: `tally_analytics`
(role `analytics_reader`). This login can read the views and nothing else.

Views (defined in `db/ddl.sql`): `order_line_facts`, `revenue_by_month`, `top_products`,
`low_stock`, `unpaid_invoices`, `stock_movement_facts`, `daily_stock_levels`,
`order_status_changes`, `order_cycle_times`.

New report? Add a view to `ddl.sql` with a test in `db/tests/analytics_test.sql`, then expose
it here. That way Tableau and the API share the same definition.

## Tableau

Use Tableau's PostgreSQL connector.

- Local: `localhost:5432`, database `tally`, user `tally_analytics`, password `tally`.
- Supabase: the analytics login and the pooler host, with SSL required.

Pick tables from the `analytics` schema. `order_line_facts` and `daily_stock_levels` are the
main data sources.

**Done:** `GET /reports/revenue-by-month`, `GET /reports/low-stock` (admin and sales only).

**To do:** endpoints for the remaining views, the Tableau workbook.
