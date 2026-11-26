"""Fresh applications and an explicit test database for auth tests."""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.main import create_app
from tally_common.config import get_settings
from tally_common.db import get_session

DEVELOPMENT_DATABASE_URL = os.environ.get("DATABASE_URL")


@pytest.fixture(autouse=True)
def test_settings(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "auth-tests-secret-at-least-32-bytes-long")
    monkeypatch.setenv(
        "DATABASE_URL",
        os.environ.get("TEST_DATABASE_URL", "postgresql://unused@localhost/unused"),
    )
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    def unused_session():
        yield None

    app.dependency_overrides[get_session] = unused_session
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="session")
def engine():
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        pytest.skip("Set TEST_DATABASE_URL to a separate seeded test database")

    target = make_url(test_url)
    if DEVELOPMENT_DATABASE_URL:
        development = make_url(DEVELOPMENT_DATABASE_URL)
        if (target.host, target.port or 5432, target.database) == (
            development.host, development.port or 5432, development.database
        ):
            pytest.fail("TEST_DATABASE_URL must point to a different database than DATABASE_URL")

    engine = create_engine(target.set(drivername="postgresql+psycopg"), pool_pre_ping=True)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine):
    # Endpoint commits release a savepoint. The enclosing transaction always rolls back.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            yield session
        transaction.rollback()


@pytest.fixture
def db_client(app, session):
    def test_session():
        yield session

    app.dependency_overrides[get_session] = test_session
    with TestClient(app) as client:
        yield client
