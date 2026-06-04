"""Database access via the Supabase client (PostgREST).

The app talks to Supabase over its REST API using the service-role key
(server-side only; it bypasses RLS). Raw SQL migrations under
`supabase/migrations/` remain the single source of truth for the schema.

Atomicity note: PostgREST does not provide multi-statement transactions across
separate client calls. If a future flow needs several writes to commit together
(e.g. writing an adjudication and updating usage accumulators), implement it as a
Postgres function and call it atomically via `get_supabase().rpc(name, params)`.
This module is intentionally not imported by the pure-domain unit tests.
"""
from functools import lru_cache

from supabase import Client, create_client

from app.config import get_settings


@lru_cache
def get_supabase() -> Client:
    """Create (once) and return the Supabase client."""
    settings = get_settings()
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
