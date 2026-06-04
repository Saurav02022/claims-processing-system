-- ============================================================
-- Manual-review completion support.
-- A line item routed to needs_review (billed over the review threshold) must be
-- resolvable by a reviewer: the claim's `under_review` state needs an exit to
-- approved/denied. This adds the data the new POST /claims/{id}/lines/{id}/review
-- flow relies on, consistent with the versioned-adjudication model.
--   1. Allow adjudication rows produced by a reviewer (triggered_by = 'review'),
--      alongside the existing 'submission' / 'dispute' triggers.
--   2. Seed reason codes that explain a manual-review approval / denial.
-- Additive and idempotent; existing rows already satisfy the widened constraint.
-- ============================================================

alter table public.adjudication drop constraint adjudication_triggered_by_check;
alter table public.adjudication add constraint adjudication_triggered_by_check
  check (triggered_by in ('submission', 'dispute', 'review'));

insert into public.reason_code (code, category, default_message) values
  ('MANUAL_REVIEW_APPROVED', 'adjustment', 'A reviewer approved the line item after manual review.'),
  ('MANUAL_REVIEW_DENIED',   'denial',     'A reviewer denied the line item after manual review.')
on conflict (code) do nothing;
