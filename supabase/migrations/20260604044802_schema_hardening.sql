-- ============================================================
-- Schema hardening (addresses Supabase advisor findings):
--  1. Drop the leftover `ensure_rls` event trigger + rls_auto_enable() function.
--     RLS is enabled explicitly per table in the baseline migration; this
--     inherited auto-enable guardrail is redundant, was not part of our
--     migration history (reproducibility gap), and exposed a SECURITY DEFINER
--     function on the public RPC surface.
--  2. Pin search_path on set_updated_at() (function_search_path_mutable WARN).
--  3. Add covering indexes for foreign keys flagged as unindexed.
-- ============================================================

-- 1. remove leftover auto-RLS guardrail (we manage RLS explicitly)
drop event trigger if exists ensure_rls;
drop function if exists public.rls_auto_enable();

-- 2. pin search_path (pg_catalog is always implicitly searched, so now() still resolves)
create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- 3. covering indexes for unindexed foreign keys
create index if not exists idx_accumulator_service        on public.accumulator (service_type_id);
create index if not exists idx_adjudication_reason_code     on public.adjudication_reason (reason_code_id);
create index if not exists idx_coverage_rule_service        on public.coverage_rule (service_type_id);
