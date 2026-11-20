from datetime import timedelta

from app import auth
from tally_common.testing import SEED_PASSWORD, auth_header


def login(client):
    response = client.post(
        "/api/v1/auth/login", json={"email": "rep@tally.test", "password": SEED_PASSWORD}
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


def refresh(client, token):
    return client.post("/api/v1/auth/refresh", json={"refresh_token": token})


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_refresh_uses_current_role_and_issues_a_usable_access_token(db_client):
    tokens = login(db_client)
    changed = db_client.patch(
        "/api/v1/users/2/role", headers=auth_header("admin"), json={"role": "admin"}
    )
    assert changed.status_code == 200

    response = refresh(db_client, tokens["refresh_token"])
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    body = response.json()
    assert set(body) == {"access_token", "token_type"}
    assert body["token_type"] == "bearer"
    assert db_client.get("/api/v1/users", headers=bearer(body["access_token"])).status_code == 200


def test_access_and_refresh_tokens_are_not_interchangeable(db_client):
    tokens = login(db_client)
    assert refresh(db_client, tokens["access_token"]).status_code == 401
    me = db_client.get("/api/v1/auth/me", headers=bearer(tokens["refresh_token"]))
    assert me.status_code == 401


def test_expired_refresh_token_is_rejected(db_client, monkeypatch):
    monkeypatch.setattr(auth, "REFRESH_LIFETIME", timedelta(seconds=-1))
    assert refresh(db_client, login(db_client)["refresh_token"]).status_code == 401


def test_password_change_invalidates_existing_refresh_token(db_client):
    tokens = login(db_client)
    changed = db_client.patch(
        "/api/v1/auth/password",
        headers=bearer(tokens["access_token"]),
        json={"current_password": SEED_PASSWORD, "new_password": "sample-new-password-123"},
    )
    assert changed.status_code == 200
    assert refresh(db_client, tokens["refresh_token"]).status_code == 401


def test_malformed_refresh_token_is_rejected(client):
    assert refresh(client, "invalid-token").status_code == 401
