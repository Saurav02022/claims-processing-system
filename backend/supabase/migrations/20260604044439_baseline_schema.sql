-- ============================================================
-- Claims Processing System — baseline schema
-- All money is NUMERIC(12,2); coinsurance NUMERIC(5,4) in 0..1.
-- Status fields use text + CHECK (evolvable in migrations).
-- UUID PKs via gen_random_uuid(); updated_at via trigger.
-- RLS enabled default-deny on every table (server-side service role only).
-- ============================================================

-- ---- shared updated_at trigger function ----
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---- lookups ----
create table public.service_type (
  id          uuid primary key default gen_random_uuid(),
  code        text not null unique,
  name        text not null,
  description text,
  active      boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);

create table public.reason_code (
  id              uuid primary key default gen_random_uuid(),
  code            text not null unique,
  category        text not null check (category in ('denial','review','adjustment')),
  default_message text not null,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

-- ---- benefit design ----
create table public.plan (
  id                      uuid primary key default gen_random_uuid(),
  name                    text not null,
  annual_deductible_amount numeric(12,2) not null default 0 check (annual_deductible_amount >= 0),
  currency                text not null default 'USD',
  active                  boolean not null default true,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now()
);

create table public.coverage_rule (
  id                      uuid primary key default gen_random_uuid(),
  plan_id                 uuid not null references public.plan(id) on delete cascade,
  service_type_id         uuid not null references public.service_type(id) on delete restrict,
  is_covered              boolean not null default true,
  annual_limit_amount     numeric(12,2) check (annual_limit_amount is null or annual_limit_amount >= 0),
  annual_visit_limit      integer check (annual_visit_limit is null or annual_visit_limit >= 0),
  copay_amount            numeric(12,2) not null default 0 check (copay_amount >= 0),
  coinsurance_rate        numeric(5,4) not null default 0 check (coinsurance_rate >= 0 and coinsurance_rate <= 1),
  review_threshold_amount numeric(12,2) check (review_threshold_amount is null or review_threshold_amount >= 0),
  effective_from          date not null default current_date,
  effective_to            date,
  created_at              timestamptz not null default now(),
  updated_at              timestamptz not null default now(),
  constraint coverage_rule_effective_dates_chk check (effective_to is null or effective_to >= effective_from),
  constraint coverage_rule_unique_version unique (plan_id, service_type_id, effective_from)
);

-- ---- member & policy ----
create table public.member (
  id                  uuid primary key default gen_random_uuid(),
  full_name           text not null,
  date_of_birth       date,
  external_member_ref text unique,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
comment on column public.member.full_name is 'PHI: member name';
comment on column public.member.date_of_birth is 'PHI: member date of birth';

create table public.policy (
  id                   uuid primary key default gen_random_uuid(),
  policy_number        text not null unique,
  member_id            uuid not null references public.member(id) on delete restrict,
  plan_id              uuid not null references public.plan(id) on delete restrict,
  status               text not null default 'active' check (status in ('active','terminated')),
  effective_from       date not null default current_date,
  effective_to         date,
  benefit_period_start date not null,
  benefit_period_end   date not null,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  constraint policy_effective_dates_chk check (effective_to is null or effective_to >= effective_from),
  constraint policy_benefit_period_chk check (benefit_period_end >= benefit_period_start)
);

-- ---- usage accumulators (materialized) ----
create table public.accumulator (
  id                    uuid primary key default gen_random_uuid(),
  policy_id             uuid not null references public.policy(id) on delete cascade,
  service_type_id       uuid references public.service_type(id) on delete cascade, -- null = policy-wide (deductible)
  period_start          date not null,
  period_end            date not null,
  amount_used           numeric(12,2) not null default 0 check (amount_used >= 0),
  visits_used           integer not null default 0 check (visits_used >= 0),
  deductible_met_amount numeric(12,2) not null default 0 check (deductible_met_amount >= 0),
  created_at            timestamptz not null default now(),
  updated_at            timestamptz not null default now(),
  constraint accumulator_period_chk check (period_end >= period_start)
);
-- nullable service_type_id => plain UNIQUE treats NULLs as distinct; use partial unique indexes:
create unique index accumulator_unique_service    on public.accumulator (policy_id, service_type_id, period_start) where service_type_id is not null;
create unique index accumulator_unique_policywide on public.accumulator (policy_id, period_start) where service_type_id is null;

-- ---- claim & line items ----
create table public.claim (
  id                  uuid primary key default gen_random_uuid(),
  claim_number        text not null unique,
  policy_id           uuid not null references public.policy(id) on delete restrict,
  status              text not null default 'submitted'
                        check (status in ('submitted','under_review','approved','partially_approved','denied','paid','disputed')),
  provider_name       text,
  provider_identifier text,
  total_billed_amount numeric(12,2) not null default 0 check (total_billed_amount >= 0),
  total_payable_amount numeric(12,2) check (total_payable_amount is null or total_payable_amount >= 0),
  submitted_at        timestamptz not null default now(),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);
comment on column public.claim.provider_name is 'PHI: provider details';
comment on column public.claim.provider_identifier is 'PHI: provider identifier';

create table public.claim_line_item (
  id              uuid primary key default gen_random_uuid(),
  claim_id        uuid not null references public.claim(id) on delete cascade,
  line_number     integer not null,
  service_type_id uuid not null references public.service_type(id) on delete restrict,
  service_date    date not null,
  billed_amount   numeric(12,2) not null check (billed_amount >= 0),
  quantity        integer not null default 1 check (quantity > 0),
  diagnosis_code  text,
  status          text not null default 'pending'
                    check (status in ('pending','approved','denied','needs_review','paid')),
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  constraint claim_line_item_unique_line unique (claim_id, line_number)
);
comment on column public.claim_line_item.diagnosis_code is 'PHI: diagnosis code';

-- ---- adjudication (versioned) & explanations ----
create table public.adjudication (
  id                 uuid primary key default gen_random_uuid(),
  line_item_id       uuid not null references public.claim_line_item(id) on delete cascade,
  sequence           integer not null,
  is_current         boolean not null default true,
  decision           text not null check (decision in ('approved','denied','needs_review')),
  covered_amount     numeric(12,2) not null default 0 check (covered_amount >= 0),
  deductible_applied numeric(12,2) not null default 0 check (deductible_applied >= 0),
  copay_amount       numeric(12,2) not null default 0 check (copay_amount >= 0),
  coinsurance_amount numeric(12,2) not null default 0 check (coinsurance_amount >= 0),
  payable_amount     numeric(12,2) not null default 0 check (payable_amount >= 0),
  triggered_by       text not null default 'submission' check (triggered_by in ('submission','dispute')),
  adjudicated_at     timestamptz not null default now(),
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint adjudication_unique_sequence unique (line_item_id, sequence)
);
-- exactly one current adjudication per line item:
create unique index adjudication_one_current on public.adjudication (line_item_id) where is_current;

create table public.adjudication_reason (
  id              uuid primary key default gen_random_uuid(),
  adjudication_id uuid not null references public.adjudication(id) on delete cascade,
  reason_code_id  uuid not null references public.reason_code(id) on delete restrict,
  message         text not null,
  detail          jsonb,
  created_at      timestamptz not null default now()
);

-- ---- state transition audit (append-only) ----
create table public.claim_status_history (
  id          uuid primary key default gen_random_uuid(),
  claim_id    uuid not null references public.claim(id) on delete cascade,
  from_status text,
  to_status   text not null,
  reason      text,
  changed_by  text not null default 'system',
  changed_at  timestamptz not null default now()
);

create table public.line_item_status_history (
  id           uuid primary key default gen_random_uuid(),
  line_item_id uuid not null references public.claim_line_item(id) on delete cascade,
  from_status  text,
  to_status    text not null,
  reason       text,
  changed_by   text not null default 'system',
  changed_at   timestamptz not null default now()
);

-- ---- disputes ----
create table public.dispute (
  id                 uuid primary key default gen_random_uuid(),
  claim_id           uuid not null references public.claim(id) on delete cascade,
  line_item_id       uuid references public.claim_line_item(id) on delete cascade, -- null = claim-level dispute
  status             text not null default 'open' check (status in ('open','under_review','resolved')),
  reason             text not null,
  resolution_outcome text check (resolution_outcome in ('upheld','overturned','partially_overturned')),
  resolution_notes   text,
  opened_at          timestamptz not null default now(),
  resolved_at        timestamptz,
  created_at         timestamptz not null default now(),
  updated_at         timestamptz not null default now(),
  constraint dispute_resolution_chk check (
    (status = 'resolved' and resolution_outcome is not null) or
    (status <> 'resolved' and resolution_outcome is null)
  )
);
comment on column public.dispute.reason is 'PHI: member free-text, may contain health information';

-- ---- secondary indexes (FK lookups + common filters) ----
create index idx_coverage_rule_plan_service     on public.coverage_rule (plan_id, service_type_id);
create index idx_policy_member                  on public.policy (member_id);
create index idx_policy_plan                     on public.policy (plan_id);
create index idx_accumulator_policy             on public.accumulator (policy_id);
create index idx_claim_policy                    on public.claim (policy_id);
create index idx_claim_status                    on public.claim (status);
create index idx_line_item_claim                 on public.claim_line_item (claim_id);
create index idx_line_item_service               on public.claim_line_item (service_type_id);
create index idx_line_item_status                on public.claim_line_item (status);
create index idx_adjudication_line_item          on public.adjudication (line_item_id);
create index idx_adjudication_reason_adj         on public.adjudication_reason (adjudication_id);
create index idx_claim_status_history_claim      on public.claim_status_history (claim_id);
create index idx_line_item_status_history_li     on public.line_item_status_history (line_item_id);
create index idx_dispute_claim                   on public.dispute (claim_id);
create index idx_dispute_line_item               on public.dispute (line_item_id);
create index idx_dispute_status                  on public.dispute (status);

-- ---- updated_at triggers (mutable tables only) ----
create trigger trg_service_type_updated_at    before update on public.service_type    for each row execute function public.set_updated_at();
create trigger trg_reason_code_updated_at      before update on public.reason_code      for each row execute function public.set_updated_at();
create trigger trg_plan_updated_at             before update on public.plan             for each row execute function public.set_updated_at();
create trigger trg_coverage_rule_updated_at    before update on public.coverage_rule    for each row execute function public.set_updated_at();
create trigger trg_member_updated_at           before update on public.member           for each row execute function public.set_updated_at();
create trigger trg_policy_updated_at           before update on public.policy           for each row execute function public.set_updated_at();
create trigger trg_accumulator_updated_at      before update on public.accumulator      for each row execute function public.set_updated_at();
create trigger trg_claim_updated_at            before update on public.claim            for each row execute function public.set_updated_at();
create trigger trg_claim_line_item_updated_at  before update on public.claim_line_item  for each row execute function public.set_updated_at();
create trigger trg_adjudication_updated_at     before update on public.adjudication     for each row execute function public.set_updated_at();
create trigger trg_dispute_updated_at          before update on public.dispute          for each row execute function public.set_updated_at();

-- ---- RLS: enable default-deny on every table (server-side service role bypasses RLS) ----
alter table public.service_type            enable row level security;
alter table public.reason_code             enable row level security;
alter table public.plan                    enable row level security;
alter table public.coverage_rule           enable row level security;
alter table public.member                  enable row level security;
alter table public.policy                  enable row level security;
alter table public.accumulator             enable row level security;
alter table public.claim                   enable row level security;
alter table public.claim_line_item         enable row level security;
alter table public.adjudication            enable row level security;
alter table public.adjudication_reason     enable row level security;
alter table public.claim_status_history    enable row level security;
alter table public.line_item_status_history enable row level security;
alter table public.dispute                 enable row level security;
