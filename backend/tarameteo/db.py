"""Database functions."""

import os

from sqlalchemy import create_engine
from sqlalchemy.engine.url import URL
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


# create_engine doesn't connect, so importing this module never touches the database.
SessionLocal = sessionmaker(
    bind=create_engine(get_db_url()),
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)
