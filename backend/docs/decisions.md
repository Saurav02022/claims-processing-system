# Decisions & Trade-offs

What was built, what was deliberately left out, and the assumptions behind the
calls. Paired with `domain-model.md` (the design) and `self-review.md` (honest
assessment).

## Architecture

- **Layered, with a pure domain core.** `app/domain/` (engine + models + enums)
  has no database or framework dependency, so the adjudication rules can be
  reasoned about and unit-tested in isolation. `claims_service` orchestrates,
  `claims_repository` persists, `main` exposes HTTP. The service depends on a
  `ClaimRepository` *protocol*, which lets the API be tested offline with a fake
  repository.
- **FastAPI interface** with five endpoints: submit claim, get claim, open
  dispute, resolve dispute, health. Enough to demonstrate the system end-to-end;
  no more.

## Data access

- **Supabase client (PostgREST), service-role key only.** The app uses
  `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` — no direct Postgres connection.
  Chosen for simplicity and because the project's direct Postgres host is
  IPv6-only (unreachable on typical IPv4 networks), whereas the REST endpoint is
  IPv4-friendly.
- **Trade-off — no atomic transactions.** PostgREST cannot wrap multiple writes in
  one transaction across calls, so a claim's rows (claim, line items,
  adjudications, reasons, accumulators, history) are written sequentially. If a
  write fails midway, partial state is possible. The fix, if needed, is a Postgres
  function called via `client.rpc(...)`. Recorded, not hidden.
- **Migrations are the source of truth**, as plain SQL under
  `supabase/migrations/`, versioned in git.

## Domain & schema

1. **Line item is the unit of adjudication**; claim status is a roll-up.
2. **Plan layer kept** — `plan` holds the benefit design, `policy` is a member's
   enrolled instance, so designs can be shared and accumulators scoped per policy.
3. **Coverage rules are typed relational rows**, not a JSON blob / rule engine /
   DSL — columns map 1:1 to insurance concepts, are constrained at the DB level,
   and are explainable.
4. **Adjudication is versioned, not overwritten** — re-adjudication after a
   dispute inserts a new row and flips `is_current`, preserving the original for
   audit.
5. **Explanations are first-class** — every decision carries reason codes from a
   queryable taxonomy plus a human message.
6. **Usage is materialized** in `accumulator` and written back on submission, so
   the deductible and limits accumulate across claims.
7. **Status via `text` + `CHECK`**, not Postgres ENUM — easy to evolve in a
   migration. Lookups (`service_type`, `reason_code`) are tables.
8. **State transitions are audited** in append-only `*_status_history` tables.
9. **UUID PKs**; money `NUMERIC(12,2)`; coinsurance `NUMERIC(5,4)` (0..1).
10. **RLS default-deny** on all tables; only the server-side service role reads
    or writes. PHI isolated to named columns and never returned in API responses
    or written to logs.

## Adjudication rules pinned by tests

- **Money rounds HALF_UP to 2 decimals** (billing standard).
- **Precedence:** policy validity → coverage → deductible → copay → coinsurance →
  limits → review threshold.
- **The annual money limit caps the insurer-payable** amount, after cost sharing.
- **Payable is floored at 0** (copay is capped at the remainder so it can't go
  negative).
- A clean approval with no reductions is tagged `COVERED_IN_FULL`.

## Deliberately out of scope

Authentication/authorization, policy purchase / enrollment, member & provider
management, notifications, dashboards, multi-role access control. Provider details
are stored on a claim but providers are not managed as entities.

## Assumptions

- **Single currency** (USD).
- **Coverage dimensions** limited to: covered?, annual money limit, annual visit
  limit, copay, coinsurance, manual-review threshold, plus a plan-level annual
  deductible. Waiting periods / out-of-pocket maximums are not modeled.
- **`paid` is not produced by the current flow** — there is no payment step, so
  claims/line items never reach `paid` (the schema allows it for the future).
- **`quantity` on a line item is accepted but does not change the math** (billed
  amount is the line total; a line counts as one visit). Left undecided pending a
  product rule rather than inventing one.
- **Dispute resolution is line-level** — a dispute must target a line item to be
  resolved; claim-wide disputes can be opened but not resolved by the endpoint.

## Known limitations

- Writes are not atomic over PostgREST (above).
- Per-line `billed_amount` is bounded to the `NUMERIC(12,2)` range (rejected with
  422); a claim whose *total* exceeds that range is an untested edge.
- Re-adjudication reconciles the accumulator for the disputed line only.
- `member` is referenced via `policy.member_id` but never queried directly by the
  app (no member-facing endpoints, by scope).
