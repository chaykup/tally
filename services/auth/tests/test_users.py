"""Account changes against PostgreSQL, rolled back after each test."""

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.deps import password_hasher
from app.models import User
from tally_common.security import get_current_user
from tally_common.testing import auth_header

PASSWORD = "original-password-123"
NEW_PASSWORD = "replacement-password-456"


def register(db_client, email="registered@example.com"):
    response = db_client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def login(db_client, email, password=PASSWORD):
    return db_client.post("/api/v1/auth/login", json={"email": email, "password": password})


def token_header(db_client, email):
    response = login(db_client, email)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_registration_creates_customer_login_and_hides_password(db_client, session):
    created = register(db_client)
    assert set(created) == {"user_id", "email", "role"}
    assert created["role"] == "customer"

    account = session.get(User, created["user_id"])
    assert account.password_hash != PASSWORD
    assert password_hasher.verify(PASSWORD, account.password_hash)
    response = db_client.get("/api/v1/auth/me", headers=token_header(db_client, created["email"]))
    assert response.status_code == 200
    assert response.json() == created


def test_registration_duplicate_is_409_and_session_remains_usable(db_client):
    register(db_client)
    response = db_client.post(
        "/api/v1/auth/register", json={"email": "registered@example.com", "password": NEW_PASSWORD}
    )
    assert response.status_code == 409
    assert login(db_client, "registered@example.com").status_code == 200
    assert login(db_client, "registered@example.com", NEW_PASSWORD).status_code == 401
    register(db_client, "another@example.com")


@pytest.mark.parametrize("role", ["admin", "sales", "customer"])
def test_admin_can_create_each_role(db_client, role):
    response = db_client.post(
        "/api/v1/users",
        headers=auth_header("admin"),
        json={"email": "created@example.com", "password": PASSWORD, "role": role},
    )
    assert response.status_code == 201, response.text
    assert set(response.json()) == {"user_id", "email", "role"}
    assert response.json()["role"] == role
    assert login(db_client, "created@example.com").status_code == 200


def test_admin_creation_detects_existing_registered_email(db_client):
    register(db_client)
    response = db_client.post(
        "/api/v1/users",
        headers=auth_header("admin"),
        json={"email": "registered@example.com", "password": NEW_PASSWORD, "role": "admin"},
    )
    assert response.status_code == 409
    me = db_client.get("/api/v1/auth/me", headers=token_header(db_client, "registered@example.com"))
    assert me.json()["role"] == "customer"


def test_role_change_is_reflected_in_me_and_new_tokens(db_client):
    user = register(db_client)
    old_header = token_header(db_client, user["email"])
    response = db_client.patch(
        f"/api/v1/users/{user['user_id']}/role",
        headers=auth_header("admin"),
        json={"role": "sales"},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {**user, "role": "sales"}
    assert db_client.get("/api/v1/auth/me", headers=old_header).json()["role"] == "sales"

    fresh = login(db_client, user["email"])
    assert fresh.status_code == 200
    verified = get_current_user(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=fresh.json()["access_token"])
    )
    assert verified.role == "sales"
    fresh_header = {"Authorization": f"Bearer {fresh.json()['access_token']}"}
    assert db_client.get("/api/v1/auth/me", headers=fresh_header).json()["role"] == "sales"
    assert db_client.get("/api/v1/users", headers=fresh_header).status_code == 403


def test_admin_demotion_keeps_existing_tokens_until_expiry(db_client):
    created = db_client.post(
        "/api/v1/users",
        headers=auth_header("admin"),
        json={"email": "temporary-admin@example.com", "password": PASSWORD, "role": "admin"},
    ).json()
    old_header = token_header(db_client, created["email"])
    response = db_client.patch(
        f"/api/v1/users/{created['user_id']}/role",
        headers=auth_header("admin"),
        json={"role": "customer"},
    )
    assert response.status_code == 200
    assert db_client.get("/api/v1/users", headers=old_header).status_code == 200
    assert db_client.get("/api/v1/users", headers=token_header(db_client, created["email"])).status_code == 403


def test_unknown_user_role_update_is_404(db_client):
    response = db_client.patch(
        "/api/v1/users/2147483647/role", headers=auth_header("admin"), json={"role": "sales"}
    )
    assert response.status_code == 404


def test_password_change_checks_current_password_and_only_updates_caller(db_client, session):
    user = register(db_client)
    headers = token_header(db_client, user["email"])
    admin_hash = session.get(User, 1).password_hash

    wrong = db_client.patch(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": "incorrect", "new_password": NEW_PASSWORD},
    )
    assert wrong.status_code == 400
    assert login(db_client, user["email"]).status_code == 200

    changed = db_client.patch(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json() == {"message": "Password updated"}
    assert login(db_client, user["email"]).status_code == 401
    assert login(db_client, user["email"], NEW_PASSWORD).status_code == 200
    assert db_client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert session.get(User, 1).password_hash == admin_hash

    retry = db_client.patch(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": "another-password-789"},
    )
    assert retry.status_code == 400


def test_deleted_account_cannot_change_password(db_client, session):
    user = register(db_client)
    headers = token_header(db_client, user["email"])
    account = session.scalar(select(User).where(User.user_id == user["user_id"]))
    session.delete(account)
    session.commit()

    response = db_client.patch(
        "/api/v1/auth/password",
        headers=headers,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert response.status_code == 401
    assert db_client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_user_list_pagination_is_ordered_and_bounded(db_client):
    headers = auth_header("admin")
    full = db_client.get("/api/v1/users", headers=headers).json()
    first = db_client.get("/api/v1/users?limit=1", headers=headers)
    second = db_client.get("/api/v1/users?limit=1&offset=1", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == full[:1]
    assert second.json() == full[1:2]
    assert db_client.get("/api/v1/users?offset=999999", headers=headers).json() == []


def test_existing_unversioned_clients_can_still_login_and_read_accounts(db_client):
    response = db_client.post(
        "/auth/login", json={"email": "admin@tally.test", "password": "password"}
    )
    assert response.status_code == 200
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert db_client.get("/auth/me", headers=headers).status_code == 200
    assert db_client.get("/users", headers=headers).status_code == 200
