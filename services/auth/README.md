# Auth service

Port **8001**. Owns schema **`accounts`** (users). DB login: `tally_auth` (role `auth_service`).

Issues the JWT access tokens every other service accepts. Tokens carry `sub` (user_id),
`email` and `role`, and expire after `ACCESS_TOKEN_MINUTES` (default 15). Token creation and
checking live in `shared/tally_common/security.py`.

Only this service can read password hashes or change users. Other services can read
`user_id, email, role, created_at`.

**Done:** `POST /auth/login`, `GET /auth/me`, `GET /users` (admin only).

**To do:** creating users and registration, changing passwords and roles, refresh tokens
(optional). Before building your own login system, consider Supabase Auth.
