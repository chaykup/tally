from fastapi.testclient import TestClient

from app.main import app
from tally_common.testing import SEED_PASSWORD, auth_header, requires_db

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok", "service": "auth"}


@requires_db
def test_login_then_me():
    response = client.post("/auth/login", json={"email": "admin@tally.test", "password": SEED_PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json() == {"user_id": 1, "email": "admin@tally.test", "role": "admin"}


@requires_db
def test_wrong_password_and_unknown_email_look_the_same():
    wrong = client.post("/auth/login", json={"email": "admin@tally.test", "password": "nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@tally.test", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


@requires_db
def test_list_users_is_admin_only():
    assert client.get("/users", headers=auth_header("admin")).status_code == 200
    assert client.get("/users", headers=auth_header("sales")).status_code == 403
    assert client.get("/users").status_code == 401
