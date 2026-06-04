"""Application configuration, loaded from environment variables.

Secrets are never committed; see `.env.example` for the expected variables and
keep real values in a local `.env` (git-ignored).
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Direct Postgres connection (Supabase connection string / pooler).
    # Used by the adjudication + persistence layer because adjudication writes
    # the decision and updates usage accumulators in a single transaction.
    # Format: postgresql+psycopg://USER:PASSWORD@HOST:PORT/postgres
    database_url: str

    # Supabase REST endpoint + service-role key. Optional here; reserved for
    # any REST-based access. The service role is server-side only (no end-user
    # auth in scope) and must never be exposed to a client.
    supabase_url: str | None = None
    supabase_service_role_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Loaded lazily so that importing the package (e.g. in pure-domain unit
    tests) does not require any environment configuration.
    """
    return Settings()
