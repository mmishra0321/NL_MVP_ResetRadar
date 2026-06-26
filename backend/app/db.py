"""SQLite engine + session factory for the Reset Radar backend.

Uses SQLAlchemy 2.0-style declarative base. Schema is defined in
`app/models.py`; this module just owns the engine and the `init_db()`
function called once at startup.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Single declarative base shared by every ORM model in the app."""


engine = create_engine(
    settings.database_url,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables defined on `Base.metadata`. Idempotent.

    Called once from `main.py` on FastAPI startup.
    """
    # Importing models for side-effect of registering them on Base.metadata.
    from app import models                                       # noqa: F401

    Base.metadata.create_all(bind=engine)


@contextmanager
def db_session() -> Iterator[Session]:
    """Per-request session context manager.

    Usage in a FastAPI route:
        with db_session() as db:
            db.add(row)
            db.commit()
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


__all__ = ["Base", "engine", "SessionLocal", "init_db", "db_session"]
