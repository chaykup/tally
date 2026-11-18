from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from tally_common.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping drops connections the server (or Supabase's pooler) has closed.
    # If you connect through Supabase's *transaction* pooler (port 6543), also pass
    # poolclass=NullPool and connect_args={"prepare_threshold": None}.
    return create_engine(get_settings().sqlalchemy_url, pool_pre_ping=True)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request. Call session.commit() to save changes."""
    with Session(get_engine()) as session:
        yield session
