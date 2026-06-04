"""Database access via the Supabase client (PostgREST).

The app talks to Supabase over its REST API using the service-role key
(server-side only; it bypasses RLS). Raw SQL migrations under
`supabase/migrations/` remain the single source of truth for the schema.

Atomicity note: PostgREST does not provide multi-statement transactions across
separate client calls. The claim-submission write therefore commits as a single
transaction through the `submit_claim_atomic` Postgres function, called via
`get_supabase().rpc(name, params)` (see `claims_repository.save_claim`).
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
