from tally_common.testing import SEED_PASSWORD, auth_header


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "auth"}


def test_login_then_me(db_client):
    response = db_client.post("/api/v1/auth/login", json={"email": "admin@tally.test", "password": SEED_PASSWORD})
    assert response.status_code == 200
    token = response.json()["access_token"]

    me = db_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json() == {"user_id": 1, "email": "admin@tally.test", "role": "admin"}


def test_wrong_password_and_unknown_email_look_the_same(db_client):
    wrong = db_client.post("/api/v1/auth/login", json={"email": "admin@tally.test", "password": "nope"})
    unknown = db_client.post("/api/v1/auth/login", json={"email": "ghost@tally.test", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_list_users_is_admin_only(db_client):
    assert db_client.get("/api/v1/users", headers=auth_header("admin")).status_code == 200
    assert db_client.get("/api/v1/users", headers=auth_header("sales")).status_code == 403
    assert db_client.get("/api/v1/users").status_code == 401
