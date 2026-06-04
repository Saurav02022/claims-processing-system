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

    # Supabase REST endpoint and service-role key. The service role is
    # server-side only (no end-user auth in scope), bypasses RLS, and must never
    # be exposed to a client. These are the only credentials the app needs.
    supabase_url: str
    supabase_service_role_key: str


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Loaded lazily so that importing the package (e.g. in pure-domain unit
    tests) does not require any environment configuration.
    """
    return Settings()
