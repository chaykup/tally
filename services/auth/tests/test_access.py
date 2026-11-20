"""Route coverage, permissions and validation without a database connection."""

import pytest

from app.main import create_app
from tally_common.testing import auth_header

ADMIN_ROUTES = [("GET", "/api/v1/users"), ("POST", "/api/v1/users"), ("PATCH", "/api/v1/users/{user_id}/role")]
PROTECTED_ROUTES = ADMIN_ROUTES + [("GET", "/api/v1/auth/me"), ("PATCH", "/api/v1/auth/password")]


def test_every_auth_and_user_route_is_covered(client):
    routes = {
        (method, path)
        for path, operations in client.app.openapi()["paths"].items()
        for method in operations
    }
    assert routes == {
        (method.lower(), path) for method, path in PROTECTED_ROUTES
    } | {
        ("get", "/health"),
        ("post", "/api/v1/auth/login"),
        ("post", "/api/v1/auth/register"),
        ("post", "/api/v1/auth/refresh"),
    }


@pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
def test_protected_routes_require_login(client, method, path):
    assert client.request(method, path.replace("{user_id}", "2"), json={}).status_code == 401


@pytest.mark.parametrize("role", ["sales", "customer"])
@pytest.mark.parametrize("method,path", ADMIN_ROUTES)
def test_user_management_requires_admin(client, role, method, path):
    response = client.request(
        method, path.replace("{user_id}", "2"), headers=auth_header(role), json={}
    )
    assert response.status_code == 403


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("POST", "/api/v1/auth/register", {"email": "invalid", "password": "long-password-123"}),
        ("POST", "/api/v1/auth/register", {"email": "new@example.com", "password": "short"}),
        ("POST", "/api/v1/auth/register", {"email": "new@example.com", "password": "x" * 129}),
        ("POST", "/api/v1/auth/register", {"email": "new@example.com", "password": "long-password-123", "role": "admin"}),
        ("POST", "/api/v1/users", {"email": "new@example.com", "password": "long-password-123", "role": "owner"}),
        ("POST", "/api/v1/users", {"email": "new@example.com", "password": "short", "role": "sales"}),
        ("POST", "/api/v1/users", {"email": "invalid", "password": "long-password-123", "role": "sales"}),
        ("PATCH", "/api/v1/users/2/role", {"role": "owner"}),
        ("PATCH", "/api/v1/users/0/role", {"role": "sales"}),
        ("PATCH", "/api/v1/auth/password", {"current_password": "old", "new_password": "short"}),
        ("PATCH", "/api/v1/auth/password", {"current_password": "old", "new_password": "x" * 129}),
        ("PATCH", "/api/v1/auth/password", {"current_password": "old", "new_password": "long-password-123", "user_id": 1}),
    ],
)
def test_invalid_input_is_422(client, method, path, payload):
    assert client.request(method, path, headers=auth_header("admin"), json=payload).status_code == 422


@pytest.mark.parametrize("query", ["limit=0", "limit=1001", "offset=-1"])
def test_invalid_pagination_is_422(client, query):
    response = client.get(f"/api/v1/users?{query}", headers=auth_header("admin"))
    assert response.status_code == 422


def test_factory_creates_independent_apps():
    first = create_app()
    second = create_app()
    first.state.example = "first app only"
    assert not hasattr(second.state, "example")
    assert first.dependency_overrides is not second.dependency_overrides
