# Tally

Order and inventory management for sales teams: four FastAPI services sharing one
PostgreSQL database, with one Postgres schema per service. Production runs on Supabase;
everyone develops and tests locally in Docker.

## Repository layout

```
db/
  ddl.sql               the whole schema: tables, triggers, analytics views, role grants
  tests/                SQL tests for constraints, privileges, analytics views
  local/                Docker-only: dev logins and seed data (never run on Supabase)
  run-tests.sh          runs db/tests in a scratch database
shared/                 tally_common: settings, DB sessions, JWT auth, change labels
services/
  auth/                 logins, tokens, users            → schema accounts
  inventory/            products, warehouses, stock      → schema inventory
  transactions/         customers, orders, invoices      → schema sales
  analytics/            reports over analytics views     → schema analytics (+ Tableau)
docker-compose.yml      db + all four services
```

Every service has the same shape:

```
services/<name>/
  app/main.py           FastAPI app, includes the routers
  app/models.py         SQLAlchemy models for this service's schema
  app/<feature>.py      one router per feature (products.py, customers.py, ...)
  tests/                pytest
  requirements.txt      this service's dependencies (pinned)
  Dockerfile
```

## Who owns what

| Service | Folder | Port | Schema | DB role | Owner |
|---|---|---|---|---|---|
| Auth / users | `services/auth` | 8001 | `accounts` | `auth_service` | _name_ |
| Inventory | `services/inventory` | 8002 | `inventory` | `inventory_service` | _name_ |
| Transactions | `services/transactions` | 8003 | `sales` | `sales_service` | _name_ |
| Analytics | `services/analytics` | 8004 | `analytics` | `analytics_reader` | _name_ |

Work inside your own folder. Changes to `db/ddl.sql` or `shared/` affect everyone, so put
them in their own PR and get the group to review it.

## Getting started

Requires Docker Desktop. Nothing else needs to be installed.

```bash
git clone <repo-url> && cd tally
cp .env.example .env
docker compose up -d --build
```

Open the interactive API docs:

- Auth: http://localhost:8001/docs
- Inventory: http://localhost:8002/docs
- Transactions: http://localhost:8003/docs
- Analytics: http://localhost:8004/docs

To call a protected endpoint, log in through `POST /auth/login` on the auth docs page,
copy the `access_token`, and click **Authorize** on any service's docs page. The same
token works on every service.

Seed logins (password for all: `password`):

| Email | Role |
|---|---|
| admin@tally.test | admin |
| rep@tally.test | sales |
| cust@tally.test | customer |

Code changes reload automatically. Rebuild after editing a `requirements.txt`:
`docker compose up -d --build <service>`.

To connect a database tool (TablePlus, DBeaver, psql): `localhost:5432`, database `tally`,
user `tally`, password `tally`. That is the superuser. To see only what your service can
see, use its login: `tally_auth`, `tally_inventory`, `tally_transactions` or
`tally_analytics`, all with password `tally`.

## Running tests

These are the same checks CI runs on every pull request.

```bash
docker compose exec db sh /db/run-tests.sh     # database tests
docker compose exec auth pytest                # one service (auth, inventory, transactions, analytics)
```

Reset the database to a clean schema plus seed data (wipes local data):

```bash
docker compose down -v && docker compose up -d --build
```

## Rules of the road

1. **The schema lives in `db/ddl.sql`.** Models in `app/models.py` only map onto it.
   Never call `Base.metadata.create_all()`. To change a table, edit `ddl.sql`, add a test
   in `db/tests/`, then update the model.
2. **Always use full table names:** `inventory.stock`, `sales.orders`. Set
   `__table_args__ = {"schema": "..."}` on every model.
3. **Your service can only touch its own schema.** The database enforces this through
   your service's login. If you get `permission denied`, you need another service's API
   or a grant change in `ddl.sql`, not a workaround.
4. **Label stock and order changes.** Before changing `inventory.stock.quantity`, call
   `tally_common.audit.set_change_context(session, movement_reason=..., order_id=..., user_id=...)`
   in the same transaction. Triggers record the history automatically.
5. **Auth comes from the token.** Use `get_current_user` or `require_roles(...)` from
   `tally_common.security`. Don't query `accounts.users` to check roles.
6. **Branches and PRs:** branch off `main` with `feat/<service>-<thing>`, for example
   `feat/inventory-receipts`. Open a PR and merge only when CI is green.

## Production (Supabase)

Run `db/ddl.sql` once in the Supabase SQL editor. Then create one login per service,
as described at the top of `ddl.sql`, and set each service's `DATABASE_URL` to its own
login (see `.env.example`). Never run anything in `db/local/` on Supabase.
