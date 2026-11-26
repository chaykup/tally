import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from tally_common.config import get_settings
from tally_common.security import CurrentUser, create_access_token, get_current_user, require_roles


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret-at-least-32-bytes-long!")
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused@localhost/unused")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/me")
    def me(user: CurrentUser = Depends(get_current_user)):
        return {"user_id": user.user_id, "role": user.role}

    @app.get("/admin-only", dependencies=[Depends(require_roles("admin"))])
    def admin_only():
        return {"ok": True}

    return TestClient(app)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_token_round_trip(client):
    token = create_access_token(7, "rep@tally.test", "sales")
    assert client.get("/me", headers=auth(token)).json() == {"user_id": 7, "role": "sales"}


def test_missing_token_is_401(client):
    assert client.get("/me").status_code == 401


def test_token_signed_with_another_secret_is_401(client):
    forged = jwt.encode({"sub": "1", "email": "x", "role": "admin", "exp": 9999999999}, "a-different-secret-also-32-bytes-long", "HS256")
    assert client.get("/me", headers=auth(forged)).status_code == 401


def test_expired_token_is_401(client):
    expired = jwt.encode({"sub": "1", "email": "x", "role": "admin", "exp": 1}, "test-secret-at-least-32-bytes-long!", "HS256")
    assert client.get("/me", headers=auth(expired)).status_code == 401


def test_require_roles(client):
    assert client.get("/admin-only", headers=auth(create_access_token(1, "a", "admin"))).status_code == 200
    assert client.get("/admin-only", headers=auth(create_access_token(2, "r", "sales"))).status_code == 403


def test_supabase_url_gets_psycopg_driver():
    url = "postgresql://postgres.ref:pw@host:5432/postgres"
    settings = get_settings().model_copy(update={"database_url": url})
    assert settings.sqlalchemy_url == "postgresql+psycopg://postgres.ref:pw@host:5432/postgres"
