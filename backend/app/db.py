"""Database access layer.

A thin wrapper over a SQLAlchemy Engine (psycopg v3 driver). We deliberately do
not use the ORM: raw SQL migrations under `supabase/migrations/` remain the
single source of truth for the schema, avoiding ORM/migration drift.

The engine and `transaction()` helper exist so the adjudication engine can later
write a decision and update usage accumulators atomically in one transaction.
This module is intentionally not imported by the pure-domain unit tests.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from app.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create (once) and return the SQLAlchemy engine."""
    settings = get_settings()
    return create_engine(settings.database_url, pool_pre_ping=True, future=True)


@contextmanager
def transaction() -> Iterator[Connection]:
    """Yield a connection inside a transaction.

    Commits on success, rolls back on exception. This is the unit of atomicity
    for adjudication: decision rows and accumulator updates commit together.
    """
    engine = get_engine()
    with engine.begin() as conn:
        yield conn
