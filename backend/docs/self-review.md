# Self-Review

An honest assessment of the system as it stands — what I'm confident in, what is
thin or rough, and what I'd do next. Calibrated, not promotional.

## What's solid

- **The adjudication engine.** `app/domain/` is pure (no DB/framework), so the
  rules are easy to read, reason about, and test. The full money pipeline
  (deductible → copay → coinsurance → limits → review), precedence, HALF_UP
  rounding, payable flooring, and claim roll-up are all covered by focused unit
  tests, including edge cases (rounding, exact-limit boundary, payable invariant,
  rule precedence).
- **Clean separation of concerns.** Engine ↔ service ↔ repository ↔ API, with the
  service depending on a repository *protocol*. This let me test the whole API
  layer offline with a fake repository, and swap in Supabase for real.
- **Explanations.** Every decision carries reason codes + messages; nothing is a
  silent number.
- **Honest schema.** All 14 tables are used by the running app (claims,
  adjudications, accumulators, status history, disputes), with CHECK constraints,
  a one-current-adjudication index, and RLS — verified by gated DB tests.
- **Tests pass:** the full offline suite is green (engine + API + roll-up + edge
  cases), and the DB-constraint suite passes when Supabase env is configured.

## What's rough or thin

- **Writes are not atomic.** Over PostgREST, a claim's rows are written across
  several calls; a mid-write failure can leave partial state. This is the biggest
  correctness caveat. A Postgres RPC would fix it.
- **The repository's real Supabase I/O isn't covered by an automated test in the
  repo.** It was verified end-to-end manually during development (submit → persist
  → read back → dispute → re-adjudicate, plus an adversarial API battery), but
  that live suite was removed to keep scope tight. So `claims_repository`'s column
  mapping is only protected by manual verification, not CI.
- **`claims_repository.py` is ~315 lines** — slightly over the file-size guideline
  and the densest file; it could be split (claims vs disputes) if it grows.
- **Dispute resolution is line-level only.** Claim-wide disputes can be opened but
  not resolved by the endpoint.
- **Re-adjudication reconciles the accumulator for the disputed line only** — fine
  for single-line disputes, but not a full claim re-run.
- **Aggregate overflow is untested.** Per-line `billed_amount` is bounded to the
  `NUMERIC(12,2)` range (rejected with 422 — a bug I found and fixed during API
  testing), but a claim whose *total* exceeds the range is an unhandled edge.
- **Local setup needs a real Supabase project** and a manual migration apply (no
  Supabase CLI `db push` is wired up). There's no offline DB mode.
- **`quantity` is accepted but inert** — a documented undecided rule, not a
  modeled behavior.

## What I'd do with more time

1. Move the claim-write path into a Postgres function and call it via
   `client.rpc(...)` for atomicity.
2. Add a gated integration test for the repository (disposable Supabase or local
   Postgres) so the real I/O mapping is protected in CI, and wire the Supabase CLI
   for one-command schema setup.
3. Support claim-level dispute resolution and full accumulator reconciliation.
4. Property-based tests for the money math; decide and implement `quantity`
   semantics.

## Bottom line

The domain modeling and adjudication logic — the heart of the assignment — are
the strongest parts and well-tested. The main real-world gap is transactional
integrity at the persistence boundary, which is understood and documented rather
than hidden.
