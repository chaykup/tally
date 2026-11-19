# Auth service

Port **8001**. Owns schema **`accounts`** (users). DB login: `tally_auth` (role `auth_service`).

Issues the JWT access tokens every other service accepts. Tokens carry `sub` (user_id),
`email` and `role`, and expire after `ACCESS_TOKEN_MINUTES` (default 15). Token creation and
checking live in `shared/tally_common/security.py`.

Only this service can read password hashes or change users. Other services can read
`user_id, email, role, created_at`.

## Endpoints

| Endpoint | Access | Purpose |
|---|---|---|
| `POST /api/v1/auth/login` | Public | Verify email and password, then issue an access token |
| `POST /api/v1/auth/register` | Public | Create a customer login |
| `GET /api/v1/auth/me` | Signed in | Read the current account's ID, email and database role |
| `PATCH /api/v1/auth/password` | Signed in | Verify the current password and set a new one |
| `GET /api/v1/users` | Admin | List account IDs, emails and roles |
| `POST /api/v1/users` | Admin | Create an account with an assigned role |
| `PATCH /api/v1/users/{user_id}/role` | Admin | Change an existing account's role |

`GET /health` reports service availability. `/docs` documents the versioned API.
Existing `/auth/*` and `/users*` URLs also work as compatibility aliases.

User listing supports `limit` (default 100, range 1–1000) and `offset` (default 0,
minimum 0), ordered by `user_id`. Invalid paging values return 422. Errors use FastAPI's
JSON `detail` field; validation errors include the field location and reason.

Try the endpoints at http://localhost:8001/docs. Log in, copy the `access_token`,
then click **Authorize** and paste just the token.

Registration takes `email` and `password`. The server assigns the `customer` role;
supplying a role or other extra fields returns 422. It creates the login in
`accounts.users`. Creating and linking a customer profile with a sales representative
belongs to the transactions service.

Admin creation also requires `role`, one of `admin`, `sales` or `customer`. Creation
returns 201, or 409 if the email already exists. Concurrent duplicate requests are
resolved by the database's existing email constraint. New email addresses are validated
and limited to 255 characters; use an address such as `person@example.com` for local
creation checks. The existing `.test` seed accounts can still log in.

Password changes take `current_password` and `new_password` and always affect the
signed-in account. An incorrect current password returns 400. Newly created and changed
passwords must contain 12–128 characters. Only Argon2 hashes are stored, and password
hashes are excluded from API responses. Changes for the same account are serialized
with a row lock so concurrent requests verify the latest password.

Role updates take `role` and return the updated account, or 404 if the ID does not
exist. Invalid roles and nonpositive IDs return 422. Admin endpoints return 401 without
a token and 403 for sales or customer tokens.

Role checks across services use the role in the token, following the shared security
module. Existing tokens retain their permissions until expiry, including after an
admin is demoted. Newly issued tokens use the new database role. Password changes also
leave existing tokens valid until expiry. `/auth/me` reads the current database role,
which can differ from the role in an older token.

## Setup

Requires Docker Desktop with Docker Compose and Python 3.12 or newer for the native
setup and the example request commands. Run the following from the repository root
for Docker development:

```sh
docker compose up -d --build auth
```

On the first start of a fresh database volume, Docker loads `db/ddl.sql`, the local
service logins and `db/local/seed.sql`. The seed admin is `admin@tally.test` with local
password `password`. Auth runs at http://localhost:8001/docs.

For native Python development, create a virtual environment and install dependencies
from the repository root:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r services/auth/requirements.txt -r requirements-dev.txt -e shared
docker compose up -d --wait db
cd services/auth
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated key into `JWT_SECRET` in the new `.env` file, then run:

```sh
python -m uvicorn app.main:app --reload --port 8001 --env-file .env
```

Choose either the native auth process or the Docker auth container for port 8001.
`docker compose stop auth` frees the port if the container is already running.
Every service that accepts the native auth tokens must use the same signing key.

## Code layout

```text
app/
  main.py               create_app factory and versioned router registration
  models.py             maps accounts.users and accounts.user_role
  schemas.py            request validation and response models
  deps.py               admin dependency and shared account creation
  auth.py               login, registration, current account and password changes
  users.py              admin account creation, listing and role updates
tests/
  conftest.py           fresh apps and isolated test database sessions
  test_access.py        route coverage and 401/403/422 checks without a database
  test_auth.py          existing login, health and user listing checks
  test_users.py         account creation, duplicates, roles and password changes
```

## Testing

Run from the repository root:

```sh
docker compose build auth
sh services/auth/run-tests.sh -q
```

The runner starts the database if necessary, creates a uniquely named temporary test
database, loads the schema and sample data, and runs pytest with `TEST_DATABASE_URL`.
It drops that temporary database when the run finishes, including on test failures.
Each account test also rolls back its changes so tests can run in any order.

Direct `pytest` runs require `TEST_DATABASE_URL` for database tests; without it, only
the database-independent tests run. Point it at a separate, seeded database. The suite
rejects a test URL that identifies the same database as `DATABASE_URL`. CI supplies a
dedicated `tally_auth_test` database and the same setting.

## Example requests

These commands use disposable local accounts. Run once in order against the seeded
Docker setup. Registration or creation repeated with the same email returns 409.

```sh
AUTH_BASE_URL=http://localhost:8001/api/v1

# Health
curl -sS http://localhost:8001/health

# Customer registration
curl -sS "$AUTH_BASE_URL/auth/register" \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com","password":"local-customer-password-123"}'

# Admin login. Extract its token for the admin requests below.
AUTH_ADMIN_TOKEN=$(curl -fsS "$AUTH_BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@tally.test","password":"password"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')

# Current account
curl -sS "$AUTH_BASE_URL/auth/me" -H "Authorization: Bearer $AUTH_ADMIN_TOKEN"

# Paginated user list
curl -sS "$AUTH_BASE_URL/users?limit=10&offset=0" \
  -H "Authorization: Bearer $AUTH_ADMIN_TOKEN"

# Admin creates a sales login. Save the ID for the role update.
AUTH_USER_ID=$(curl -fsS "$AUTH_BASE_URL/users" \
  -H "Authorization: Bearer $AUTH_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"email":"staff@example.com","password":"local-staff-password-123","role":"sales"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["user_id"])')

# Admin changes that login's role
curl -sS -X PATCH "$AUTH_BASE_URL/users/$AUTH_USER_ID/role" \
  -H "Authorization: Bearer $AUTH_ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"role":"customer"}'

# Log in as the registered customer to change their own password
AUTH_CUSTOMER_TOKEN=$(curl -fsS "$AUTH_BASE_URL/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"person@example.com","password":"local-customer-password-123"}' \
  | python3 -c 'import json, sys; print(json.load(sys.stdin)["access_token"])')

curl -sS -X PATCH "$AUTH_BASE_URL/auth/password" \
  -H "Authorization: Bearer $AUTH_CUSTOMER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"current_password":"local-customer-password-123","new_password":"changed-customer-password-456"}'
```