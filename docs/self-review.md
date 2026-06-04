# Self-Review

An honest assessment of the system as it stands — what I'm confident in, what is
thin or rough, and what I'd do next. Calibrated, not promotional.

## What's solid

- **The adjudication engine.** `app/domain/` is pure (no DB / framework), so the
  rules are easy to read, reason about, and test. The full money pipeline
  (deductible → copay → coinsurance → limits → review), precedence, HALF_UP
  rounding, payable flooring, and the claim roll-up are covered by focused unit
  tests, including edge cases (rounding, exact-limit boundary, payable invariant,
  rule precedence).
- **Clean separation of concerns.** Engine ↔ service ↔ repository ↔ API, with the
  service depending on a repository **protocol**. This lets the whole API layer be
  tested offline with a fake repository and swapped to Supabase for real.
- **Complete claim lifecycle.** A `needs_review` line is not a dead end: a reviewer
  endpoint (`POST /claims/{id}/lines/{line_id}/review`) takes the claim out of
  `under_review` to `approved` / `partially_approved` / `denied`, writing a
  versioned adjudication (`triggered_by = review`), a status-history entry, and an
  accumulator reconciliation.
- **Atomic claim submission.** The full submission write goes through the
  `submit_claim_atomic` Postgres function via `client.rpc(...)`, so a mid-write
  failure rolls back the whole claim — verified by forcing a line-level constraint
  failure and confirming zero orphan rows.
- **Explanations.** Every decision carries reason codes + messages; nothing is a
  silent number.
- **Honest schema.** All 14 tables are used by the running app, with CHECK
  constraints, a one-current-adjudication partial unique index, accumulator
  uniqueness, and RLS — verified by gated DB tests.
- **Money presentation.** API responses serialize every monetary field as a fixed
  2-decimal string, so amounts are consistent across endpoints.

## What's rough or thin

- **Dispute/review writes are still sequential.** Claim submission is atomic, but
  dispute resolution and manual-review completion still write across several
  PostgREST calls. They touch few rows (a single line), so the blast radius of a
  mid-write failure is small, but it is a real residual — the same RPC approach
  should be extended to them.
- **Re-adjudication reconciles only the affected line.** Dispute/review recompute
  the accumulator for that one line, not a full claim re-run — fine for the
  single-line actions offered, but not a general re-adjudication.
- **The live-I/O tests are gated.** `test_repository_integration.py` (real
  `SupabaseClaimRepository` round-trips) and `test_schema_constraints.py` (DB
  constraints) run only when Supabase env vars are set; a credential-less CI run
  skips them, so the column mapping is protected locally but not in a bare CI.
- **`claims_repository.py` is ~349 lines** — the densest file; it could be split
  (claims vs disputes/review) if it grows.
- **Aggregate overflow is untested.** Per-line `billed_amount` is bounded to the
  `NUMERIC(12,2)` range (rejected with 422), but a claim whose *total* exceeds the
  range is an unhandled edge.
- **Local setup needs a real Supabase project** and a manual migration apply (no
  Supabase CLI `db push` is wired up). There is no offline DB mode for the running
  API, though the engine and API logic are fully testable offline.
- **`quantity` is accepted but inert** — a documented undecided rule, not a
  modeled behavior.

## What I'd do with more time

1. Extend the atomic-RPC approach to the dispute-resolution and manual-review
   write paths (the only remaining sequential writes).
2. Wire the Supabase CLI for one-command schema setup, and run the gated
   repository integration suite in CI against a disposable/local Postgres so the
   real I/O mapping is checked on every build.
3. Support claim-level dispute resolution and full accumulator reconciliation.
4. Property-based tests for the money math; decide and implement `quantity`
   semantics.

## Bottom line

The domain modeling and adjudication logic — the heart of the assignment — are
the strongest parts and well-tested, and the claim lifecycle is complete
(including the manual-review exit from `under_review`). Claim submission now
writes atomically via a Postgres RPC; the remaining persistence residual is that
the smaller dispute/review write paths are still sequential — understood and
documented rather than hidden.
