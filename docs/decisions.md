# Decisions & Trade-offs

What was built, what was deliberately left out, and the reasoning behind the
calls. Paired with `domain-model.md` (the design) and `self-review.md` (the honest
assessment). Where this disagrees with code, the code wins — but it is kept in
sync deliberately.

## Architecture

- **Layered, with a pure domain core.** `app/domain/` (engine + models + enums)
  has no database or framework dependency, so the adjudication rules can be
  reasoned about and unit-tested in isolation. `claims_service` orchestrates,
  `claims_repository` persists, `main` exposes HTTP. The service depends on a
  `ClaimRepository` **protocol**, which lets the API be tested offline with an
  in-memory fake repository and run against Supabase for real.
- **FastAPI REST interface, six endpoints:** submit claim, get claim, open
  dispute, resolve dispute, complete manual review, health. Enough to demonstrate
  the system end-to-end; no more.

## Data access

- **Supabase client (PostgREST), service-role key only.** The app uses
  `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` — no direct Postgres connection.
  Chosen for simplicity and because the project's direct Postgres host is
  IPv6-only (unreachable on typical IPv4 networks), whereas the REST endpoint is
  IPv4-friendly.
- **Atomic claim submission via RPC.** PostgREST cannot wrap multiple writes in
  one transaction across calls. The submission write (claim, status history, line
  items, adjudications, reasons, accumulators — the largest multi-row write) is
  therefore done in a single transaction by the `submit_claim_atomic` Postgres
  function, called via `client.rpc(...)`. A mid-write failure now rolls the whole
  submission back instead of leaving partial state. The smaller dispute-resolution
  and manual-review write paths are still sequential PostgREST calls (few rows,
  single line) — a narrower, documented residual.
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
   dispute *or* a manual-review completion inserts a new row and flips
   `is_current`, preserving the original for audit (`triggered_by` records which:
   `submission` / `dispute` / `review`). Manual review is the modeled exit from
   `under_review`: a reviewer overrides a `needs_review` line to `approved` /
   `denied`, the claim is re-rolled-up, and the accumulator is reconciled.
5. **Explanations are first-class** — every decision carries reason codes from a
   queryable taxonomy plus a human message.
6. **Usage is materialized** in `accumulator` and written back, so the deductible
   and per-service limits accumulate across claims within a benefit period.
7. **Status via `text` + `CHECK`**, not Postgres ENUM — easy to evolve in a
   migration. Lookups (`service_type`, `reason_code`) are tables.
8. **State transitions are audited** in append-only `*_status_history` tables.
9. **UUID PKs**; money `NUMERIC(12,2)`; coinsurance `NUMERIC(5,4)` (0..1).
10. **RLS default-deny** on all tables; only the server-side service role reads or
    writes. PHI is isolated to named columns and never returned in API responses
    or written to logs.

## Adjudication rules pinned by tests

- **Money rounds HALF_UP to 2 decimals** (billing standard); API responses
  serialize money as fixed 2-decimal strings.
- **Precedence:** policy validity → coverage → deductible → copay → coinsurance →
  limits → review threshold.
- **The annual money limit caps the insurer-payable** amount, after cost sharing.
- **Payable is floored at 0** (copay is capped at the remainder so it can't go
  negative).
- A clean approval with no reductions is tagged `COVERED_IN_FULL`.

## Interface decisions

- **Disputes are line-level.** `line_item_id` is required when opening a dispute
  (rejected with 422 otherwise), so every dispute has a re-adjudication target and
  a claim can never be stranded permanently in `disputed`. The DB column stays
  nullable to allow claim-level disputes as a future extension.
- **Manual review is a distinct endpoint** (`POST /claims/{id}/lines/{id}/review`)
  taking `approved` / `denied`. It overrides the engine's `needs_review` outcome —
  the engine stays pure; the human decision lives in the service layer.
- **Validation at the HTTP boundary** (Pydantic): `billed_amount` bounded to the
  `NUMERIC(12,2)` range so oversized input is a 422, not a 500 on insert;
  `quantity > 0`; at least one line item; `decision` constrained to a literal.

## Deliberately out of scope

Authentication / authorization, policy purchase / enrollment, member & provider
management, notifications, dashboards, multi-role access control. Provider details
are stored on a claim but providers are not managed as entities. No payment step,
so the `paid` states are never produced.

## Assumptions

- **Single currency** (USD).
- **Coverage dimensions** limited to: covered?, annual money limit, annual visit
  limit, copay, coinsurance, manual-review threshold, plus a plan-level annual
  deductible. Waiting periods / out-of-pocket maximums are not modeled.
- **`paid` is not produced by the current flow** — there is no payment step (the
  schema allows it for the future).
- **`quantity` on a line item is accepted but does not change the math** (the
  billed amount is the line total; a line counts as one visit). Left undecided
  pending a product rule rather than inventing one.
- **Manual review and dispute resolution are line-level.** A reviewer resolves a
  single `needs_review` line; a dispute targets a single line. There is no single
  "review/dispute the whole claim" action.

## Known limitations

- Claim submission is atomic (RPC); the dispute-resolution and manual-review write
  paths are still sequential over PostgREST.
- Re-adjudication (dispute / review) reconciles the accumulator for the affected
  line only — correct for single-line actions, not a full claim re-run.
- Per-line `billed_amount` is bounded to the `NUMERIC(12,2)` range (rejected with
  422); a claim whose *total* exceeds that range is an untested edge.
- `member` is referenced via `policy.member_id` but never queried directly by the
  app (no member-facing endpoints, by scope).
