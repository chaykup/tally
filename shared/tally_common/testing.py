"""Helpers for service tests.

Tests marked with `requires_db` talk to the real local database (started by docker compose,
loaded with db/ddl.sql and db/local/seed.sql). They are skipped when DATABASE_URL is unset.
"""

import os

import pytest

from tally_common.security import create_access_token

requires_db = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not set; start the stack with docker compose"
)

# Users created by db/local/seed.sql. Every seed user's password is "password".
SEED_USERS = {
    "admin": {"user_id": 1, "email": "admin@tally.test"},
    "sales": {"user_id": 2, "email": "rep@tally.test"},
    "customer": {"user_id": 3, "email": "cust@tally.test"},
}
SEED_PASSWORD = "password"


def auth_header(role: str) -> dict[str, str]:
    """Authorization header for the seed user with this role."""
    user = SEED_USERS[role]
    token = create_access_token(user["user_id"], user["email"], role)
    return {"Authorization": f"Bearer {token}"}
