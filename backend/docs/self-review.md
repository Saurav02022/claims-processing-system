# Self-Review

> **Living document.** Honest assessment, updated as the system grows. Right now the project is at the
> design + schema stage — no application code or tests yet.

## What's solid so far

- Clear, documented domain model with explicit entities, relationships, and two state machines.
- Schema decisions are deliberate and reviewable (versioned adjudication, typed coverage rules,
  first-class explanations, audited state transitions).
- Migration baseline was reconciled to a truthful state before any DDL — no phantom history.
- Clean git trail: design → docs → migration (→ tests → code to come).

## What's rough / not done yet

- **No application code.** The adjudication engine (the interesting part) is not written; the math is
  specified in `domain-model.md` but not implemented.
- **No tests yet.** Domain-rule tests (limit exhaustion, partial approval, dispute re-adjudication) are
  planned to be written before/alongside the engine, not after.
- **Accumulator concurrency** is designed (single-row lock per policy/service/period) but not yet
  proven under concurrent adjudication.
- **Seed/reference data** (`service_type`, `reason_code`) is a reasonable starter set, not exhaustive;
  the final reason-code taxonomy will firm up while writing adjudication tests.

## Known trade-offs I'd flag in review

- Chose a materialized accumulator over derive-on-read for atomic limit checks; accepts a small sync
  responsibility in exchange for correctness under concurrency.
- Kept the `plan` layer for realism even though a single-policy take-home could collapse it — costs one
  table, buys a cleaner model and an easy extension story.

## What I'd do with more time

- Property-based tests around the adjudication math.
- A small end-to-end demo (submit → adjudicate → dispute → re-adjudicate) wired through the API.
