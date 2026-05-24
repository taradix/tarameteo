"""Database functions."""

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
from sqlalchemy.orm import Session as DBSession
from sqlalchemy.orm import sessionmaker


def get_db_url(env=os.environ) -> URL:
    """Return a database URL from DB variables in the environment."""
    return URL.create(
        drivername=env.get("DBDRIVER", "sqlite"),
        username=env.get("DBUSER"),
        password=env.get("DBPASS"),
        host=env.get("DBHOST"),
        port=env.get("DBPORT"),
        database=env.get("DBNAME", "/data/alerts.db"),
    )


@contextmanager
def db_transaction(db: DBSession) -> Iterator[DBSession]:
    """Context manager for handling database transactions safely."""
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise


DATABASE_URL = get_db_url()

engine = create_engine(
    DATABASE_URL,
    echo=False,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


@contextmanager
def get_db_session() -> Iterator[DBSession]:
    """Yield a database session."""
    db_session = SessionLocal()
    try:
        yield db_session
    finally:
        db_session.close()
