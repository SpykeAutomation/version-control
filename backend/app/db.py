"""SQLAlchemy engine and session wiring (SQLite for the pilot)."""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

engine = create_engine(
    settings.db_url,
    connect_args={"check_same_thread": False},  # FastAPI uses a threadpool
)


@event.listens_for(engine, "connect")
def _configure_sqlite_connection(dbapi_connection, _record) -> None:
    """Per-connection SQLite setup (pragmas below are per-connection except
    journal_mode, which persists in the DB file but is idempotent to re-issue).

    - foreign_keys: SQLite ignores ON DELETE CASCADE unless enabled, so turn it
      on for every connection to keep deletes cascading.
    - journal_mode=WAL: readers no longer block the writer (and vice versa) —
      essential once many requests hit the threadpool concurrently.
    - busy_timeout: when two writers do collide, wait up to 5s for the lock
      instead of failing instantly with "database is locked".
    - synchronous=NORMAL: the documented-safe fsync level under WAL (an OS
      crash can lose the last few commits, but never corrupts the DB).
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
