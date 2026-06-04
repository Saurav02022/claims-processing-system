-- ============================================================
-- Atomic claim submission.
-- PostgREST cannot wrap multiple writes in one transaction, so a claim's rows
-- were previously written across several client calls (claim, line items,
-- adjudications, reasons, accumulators, history) — a mid-write failure could
-- leave partial state. This function performs the entire submission write in a
-- single transaction and is called from the repository via client.rpc().
--
-- SECURITY INVOKER: runs as the caller (the server-side service role, which
-- bypasses RLS). search_path is pinned and every object is schema-qualified.
-- EXECUTE is revoked from anon/authenticated so it is not on the public surface.
-- ============================================================
create or replace function public.submit_claim_atomic(payload jsonb)
returns uuid
language plpgsql
security invoker
set search_path = ''
as $$
declare
  v_claim_id     uuid;
  v_policy_id    uuid;
  v_line         jsonb;
  v_line_id      uuid;
  v_adj_id       uuid;
  v_reason       jsonb;
  v_period_start date;
  v_period_end   date;
  v_usage        jsonb;
begin
  v_policy_id := (payload->'claim'->>'policy_id')::uuid;

  insert into public.claim (claim_number, policy_id, status, provider_name,
                            provider_identifier, total_billed_amount, total_payable_amount)
  values (payload->'claim'->>'claim_number', v_policy_id, payload->'claim'->>'status',
          payload->'claim'->>'provider_name', payload->'claim'->>'provider_identifier',
          (payload->'claim'->>'total_billed_amount')::numeric,
          (payload->'claim'->>'total_payable_amount')::numeric)
  returning id into v_claim_id;

  insert into public.claim_status_history (claim_id, from_status, to_status, reason, changed_by)
  values (v_claim_id, null, payload->'claim'->>'status', 'submission', 'system');

  for v_line in select * from jsonb_array_elements(payload->'lines')
  loop
    insert into public.claim_line_item (claim_id, line_number, service_type_id, service_date,
                                        billed_amount, quantity, diagnosis_code, status)
    values (v_claim_id, (v_line->>'line_number')::int, (v_line->>'service_type_id')::uuid,
            (v_line->>'service_date')::date, (v_line->>'billed_amount')::numeric,
            (v_line->>'quantity')::int, v_line->>'diagnosis_code', v_line->>'decision')
    returning id into v_line_id;

    insert into public.adjudication (line_item_id, sequence, is_current, decision, covered_amount,
                                     deductible_applied, copay_amount, coinsurance_amount,
                                     payable_amount, triggered_by)
    values (v_line_id, 1, true, v_line->>'decision', (v_line->>'covered_amount')::numeric,
            (v_line->>'deductible_applied')::numeric, (v_line->>'copay_amount')::numeric,
            (v_line->>'coinsurance_amount')::numeric, (v_line->>'payable_amount')::numeric, 'submission')
    returning id into v_adj_id;

    for v_reason in select * from jsonb_array_elements(coalesce(v_line->'reasons', '[]'::jsonb))
    loop
      insert into public.adjudication_reason (adjudication_id, reason_code_id, message)
      select v_adj_id, rc.id, coalesce(v_reason->>'message', '')
      from public.reason_code rc
      where rc.code = v_reason->>'code';
    end loop;

    insert into public.line_item_status_history (line_item_id, from_status, to_status, reason, changed_by)
    values (v_line_id, 'pending', v_line->>'decision', 'submission', 'system');
  end loop;

  v_period_start := (payload->'accumulators'->>'period_start')::date;
  v_period_end   := (payload->'accumulators'->>'period_end')::date;

  insert into public.accumulator (policy_id, service_type_id, period_start, period_end, deductible_met_amount)
  values (v_policy_id, null, v_period_start, v_period_end,
          (payload->'accumulators'->>'deductible_met')::numeric)
  on conflict (policy_id, period_start) where service_type_id is null
  do update set deductible_met_amount = excluded.deductible_met_amount;

  for v_usage in select * from jsonb_array_elements(coalesce(payload->'accumulators'->'usage', '[]'::jsonb))
  loop
    insert into public.accumulator (policy_id, service_type_id, period_start, period_end, amount_used, visits_used)
    values (v_policy_id, (v_usage->>'service_type_id')::uuid, v_period_start, v_period_end,
            (v_usage->>'amount_used')::numeric, (v_usage->>'visits_used')::int)
    on conflict (policy_id, service_type_id, period_start) where service_type_id is not null
    do update set amount_used = excluded.amount_used, visits_used = excluded.visits_used;
  end loop;

  return v_claim_id;
end;
$$;

revoke execute on function public.submit_claim_atomic(jsonb) from public, anon, authenticated;
grant execute on function public.submit_claim_atomic(jsonb) to service_role;
