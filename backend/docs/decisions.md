# Decisions & Trade-offs

> **Living document.** Records what was built, what was deliberately skipped, and the assumptions
> behind each call. Expanded as the system grows.

## Stack

- **Python + FastAPI** for the application/interface, **Supabase (Postgres)** for persistence.
- **Migrations are the source of truth**, written as SQL under `backend/supabase/migrations/` and
  versioned in git. Rationale: the DB is Supabase-hosted; one migration mechanism avoids ORM/migration
  drift, and plain SQL is reviewable and reproducible against any Postgres.

## Database / schema decisions

1. **Line item is the unit of adjudication.** Everything else (partial approvals, per-service limits,
   per-line explanations) follows from this. The claim status is a *roll-up* of its line items.
2. **Plan layer kept.** `plan` holds the benefit design; `policy` is a member's enrolled instance.
   Separates "what the product covers" from "who is enrolled" and lets policies share a design.
3. **Coverage rules are typed relational rows**, not JSON blobs / a rule engine / a DSL. Typed columns
   (`is_covered`, limits, copay, coinsurance, review threshold) map 1:1 to insurance concepts, are
   constrained at the DB level, and are explainable. Deductible is plan-level.
4. **Adjudication is versioned, not overwritten.** Each line item can have N adjudications
   (`sequence`, exactly one `is_current`). Re-adjudication after a dispute inserts a new row, preserving
   the original decision for audit.
5. **Explanations are first-class.** `adjudication_reason` rows (reason code + human message +
   structured JSONB detail) answer "why" for every decision; `reason_code` is a queryable taxonomy.
6. **Usage tracked in a materialized `accumulator`** (per policy / service type / period), updated in the
   same transaction as adjudication, with line-item adjudications as the audit ledger for reconciliation.
7. **Status via `text` + `CHECK`**, not Postgres ENUM — CHECK constraints evolve cleanly in migrations
   (ENUMs can't drop values and can't `ADD VALUE` in a transaction). Lookups (`service_type`,
   `reason_code`) are tables for referential integrity.
8. **State transitions are audited** in append-only `*_status_history` tables.
9. **UUID PKs** (`gen_random_uuid()`); human-readable `claim_number` / `policy_number` for display.
   Money is `NUMERIC(12,2)`; coinsurance `NUMERIC(5,4)` constrained to 0..1.
10. **Migration baseline reconciled.** The project arrived with a ghost migration record
    (`20260603163415_create_claims_table`) and no matching table; it was removed so the ledger is
    truthful and our first migration is the genuine baseline.

## Migrations

- Three migrations under `backend/supabase/migrations/`, filenames matching the applied ledger
  versions for clean reproducibility:
  `baseline_schema` (DDL), `seed_reference_data` (catalog + reason codes), `schema_hardening`.
- **Applied migrations are immutable.** Advisor-driven fixes went into a new `schema_hardening`
  migration rather than editing the baseline.
- **Advisor pass after DDL:** dropped a leftover `ensure_rls` event trigger / `rls_auto_enable()`
  SECURITY DEFINER function (redundant with our explicit RLS, and not in our migration history);
  pinned `search_path` on `set_updated_at()`; added covering indexes for unindexed FKs. The only
  remaining advisories are `rls_enabled_no_policy` (INFO) — intended (see below). `unused_index`
  notices are ignored: they fire only because the DB has no query traffic yet.

## Sensitive data (PHI)

- PHI is isolated to named columns (member name/DOB, diagnosis code, provider details, dispute reason)
  and documented via `COMMENT ON COLUMN`.
- RLS is enabled default-deny on every table; only the server-side service role accesses data
  (no end-user auth in scope). PHI must not enter logs or `adjudication_reason.detail`.

## Out of scope (intentional)

Authentication, policy purchase/enrollment, member/provider account management, notifications,
dashboards, admin panels, multi-role access control. Provider details are *stored* on a claim but
providers are not managed as records. Column-level encryption is a documented non-goal.

## Assumptions

- Single currency (USD).
- Coverage dimensions limited to: covered?, annual money limit, annual visit limit, copay, coinsurance,
  manual-review threshold, plan-level annual deductible. Waiting periods / out-of-pocket maximums deferred.
- `paid` is modeled as an explicit transition (not auto-set on approval) until the lifecycle is wired.

### Adjudication assumptions surfaced by the test suite

These are encoded as expectations in `tests/test_adjudication_edge_cases.py`; the engine
implementation must honour them (or the tests must be updated with rationale):

- **Money rounds HALF_UP to 2 decimals** (standard for currency/billing).
- **The annual money limit caps the insurer-payable amount**, applied *after* cost sharing.
- **Rule precedence** follows the documented §6 step order: policy validity → coverage →
  cost sharing → limits → review threshold (e.g. a terminated policy denies `POLICY_INACTIVE`
  even with no rule; an exhausted limit denies before the review-threshold check).
- **`payable_amount` is floored at 0** — cost sharing exceeding the covered amount never goes negative.
- **`quantity` semantics are undecided** (does it multiply billed amount / count as multiple visits?).
  Intentionally left untested pending a product decision rather than asserting an invented rule.
