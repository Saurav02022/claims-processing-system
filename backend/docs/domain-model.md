# Domain Model

How the Claims Processing System models the insurance domain: the entities, how
they relate, how a line item is adjudicated, and how claims and line items move
through their lifecycles. This describes the system **as implemented** — the
database schema (`supabase/migrations/`) and the engine (`app/domain/`) are the
source of truth.

---

## Core idea

The **line item is the unit of adjudication**, not the claim. Each line item is
decided independently against the policy's coverage rules; the claim's status is
a *roll-up* of its line decisions. Partial approvals, per-service limits, and
per-line explanations all follow from this.

---

## Entities

The database has 14 tables in three groups.

**Reference / catalog**
- `service_type` — catalog of coverable services (e.g. `PHYSIO`, `DENTAL`). The
  join key between coverage rules and line items.
- `reason_code` — taxonomy of explanation codes (denial / review / adjustment).

**Benefit design & enrollment**
- `plan` — benefit design; holds the plan-wide `annual_deductible_amount`.
- `coverage_rule` — one row per (plan, service type): whether covered, annual
  money limit, annual visit limit, copay, coinsurance rate, review threshold,
  effective dates. This is the structured coverage logic.
- `member` — the insured person (PHI: name, date of birth).
- `policy` — a member's enrolled instance of a plan, with effective dates and a
  benefit period (the accumulator window) and status (`active` / `terminated`).

**Claims & adjudication**
- `claim` — a submission against a policy; holds the roll-up status, provider
  details (PHI), and billed/payable totals.
- `claim_line_item` — one billed service on a claim; the unit of adjudication.
  Holds billed facts, diagnosis code (PHI), and current status.
- `adjudication` — the decision + money breakdown for a line item. **Versioned**:
  a line can have several adjudications (`sequence`), exactly one `is_current`.
  `triggered_by` is `submission` or `dispute`.
- `adjudication_reason` — one or more explanations per adjudication (reason code +
  human message + optional JSONB detail).
- `accumulator` — usage consumed in a benefit period: a policy-wide row
  (deductible met) and per-service rows (amount used, visits used).
- `claim_status_history`, `line_item_status_history` — append-only audit of every
  status transition.
- `dispute` — a member's challenge to a decision, linked to a claim and (for
  resolution) a specific line item.

### Relationships

```mermaid
erDiagram
    member ||--o{ policy : holds
    plan ||--o{ policy : "enrolled as"
    plan ||--o{ coverage_rule : defines
    service_type ||--o{ coverage_rule : governs
    policy ||--o{ claim : "billed via"
    policy ||--o{ accumulator : "tracks usage in"
    service_type ||--o{ accumulator : "scoped to"
    claim ||--o{ claim_line_item : contains
    service_type ||--o{ claim_line_item : classifies
    claim_line_item ||--o{ adjudication : "decided by (versioned)"
    adjudication ||--o{ adjudication_reason : "explained by"
    reason_code ||--o{ adjudication_reason : categorizes
    claim ||--o{ claim_status_history : "audited by"
    claim_line_item ||--o{ line_item_status_history : "audited by"
    claim ||--o{ dispute : "challenged by"
    claim_line_item ||--o{ dispute : "optionally targets"
```

---

## Coverage rules

Coverage logic is modeled as **typed relational rows** in `coverage_rule` (not a
JSON blob or rule DSL), keyed by (plan, service type). The dimensions:

| Field | Meaning |
|---|---|
| `is_covered` | If false (or no rule) → the line is denied `NOT_COVERED`. |
| `annual_limit_amount` | Max insurer-payable per benefit period (null = unlimited). |
| `annual_visit_limit` | Max visits per period (null = unlimited). |
| `copay_amount` | Fixed member copay per line. |
| `coinsurance_rate` | Member's share (0..1) of the amount after deductible + copay. |
| `review_threshold_amount` | Billed above this → routed to manual review. |
| `effective_from` / `effective_to` | Rule validity window. |

The plan-wide deductible lives on `plan.annual_deductible_amount`.

---

## Adjudication algorithm

`adjudicate_line_item` (`app/domain/adjudication.py`) is a pure function of its
inputs. Steps run in this order — **precedence matters** and is enforced/tested:

1. **Policy validity.** Not `active` → deny `POLICY_INACTIVE`. Service date
   outside the benefit period → deny `SERVICE_DATE_OUT_OF_COVERAGE`.
2. **Coverage.** No rule, or `is_covered` false → deny `NOT_COVERED`.
3. `covered_amount = billed_amount`.
4. **Deductible.** Apply the *remaining* plan deductible
   (`plan deductible − already met`), capped at the covered amount →
   `DEDUCTIBLE_APPLIED`.
5. **Copay.** Apply the fixed copay, capped at the post-deductible remainder
   (so payable never goes negative) → `COPAY_APPLIED`.
6. **Coinsurance.** `rate × remaining` → `COINSURANCE_APPLIED`.
7. **Limits.** If visits already used ≥ visit limit → deny `VISIT_LIMIT_EXCEEDED`.
   If the annual money limit is exhausted → deny `ANNUAL_LIMIT_EXCEEDED`.
   Otherwise cap payable at the remaining limit → `LIMIT_PARTIALLY_APPLIED`.
8. **Review threshold.** If `billed > review_threshold` → `NEEDS_REVIEW`.
9. `payable = covered − deductible − copay − coinsurance`, floored at 0.

An approval with no reductions at all is tagged `COVERED_IN_FULL`.

**Conventions:** money is `Decimal` rounded **HALF_UP to 2 decimals**; the annual
money limit caps the *insurer-payable* amount (after cost sharing).

### Reason codes

`NOT_COVERED`, `POLICY_INACTIVE`, `SERVICE_DATE_OUT_OF_COVERAGE`,
`ANNUAL_LIMIT_EXCEEDED`, `VISIT_LIMIT_EXCEEDED` (denials);
`OVER_REVIEW_THRESHOLD` (review); `DEDUCTIBLE_APPLIED`, `COPAY_APPLIED`,
`COINSURANCE_APPLIED`, `LIMIT_PARTIALLY_APPLIED`, `COVERED_IN_FULL` (adjustments).
Every decision carries at least one reason — this is the explanation capability.

---

## Line-item lifecycle

The engine assigns a **decision**: `approved`, `denied`, or `needs_review`. That
decision is persisted as the line's status. The schema's `claim_line_item.status`
also allows `pending` (the insert default, before adjudication) and `paid` (a
payment step that is out of scope), but the current flow sets the status to the
decision on submission.

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> approved
    pending --> denied
    pending --> needs_review
    approved --> denied : re-adjudication (dispute)
    denied --> approved : re-adjudication (dispute)
```

## Claim lifecycle

The claim status is **derived from its line decisions** (`roll_up_claim_status`):

- no lines → `submitted`
- any line `needs_review` → `under_review`
- all `approved` → `approved`
- all `denied` → `denied`
- otherwise (mix of approved/denied) → `partially_approved`

Opening a dispute sets the claim to `disputed`; resolving it recomputes the
roll-up. (`paid` exists in the schema but is not produced by the current flow.)

```mermaid
stateDiagram-v2
    [*] --> submitted
    submitted --> approved
    submitted --> partially_approved
    submitted --> denied
    submitted --> under_review
    approved --> disputed
    partially_approved --> disputed
    denied --> disputed
    under_review --> disputed
    disputed --> approved : resolved
    disputed --> partially_approved : resolved
    disputed --> denied : resolved
    disputed --> under_review : resolved
```

### Partial approvals

Because each line is decided independently, a claim with (say) one approved, one
denied, and one review line rolls up to `under_review`, with the claim's
`total_payable_amount` summing the per-line payables.

---

## Tracking usage against limits

Usage is materialized in `accumulator`, scoped to (policy, period):
- the **policy-wide row** (`service_type_id = null`) holds `deductible_met_amount`;
- **per-service rows** hold `amount_used` (insurer payable) and `visits_used`.

On submission, the service threads the deductible and per-service usage across the
claim's line items in memory (so a multi-line claim is correct), then **writes the
updated accumulators back** so limits and the deductible carry across claims.

On dispute resolution, the disputed line is re-evaluated against the accumulators
*minus that line's own prior contribution*, and the accumulators are updated to
reflect the new result (reconciled for that one line).

---

## Disputes & re-adjudication

A `dispute` references a claim and (for resolution) a specific line item.

- **Open** (`POST /claims/{id}/disputes`): records the dispute (`open`) and sets
  the claim to `disputed`, with a status-history entry.
- **Resolve** (`POST /disputes/{id}/resolve`): re-adjudicates the disputed line
  against the *current* coverage rules. A new `adjudication` row is inserted
  (`sequence + 1`, `is_current = true`, `triggered_by = dispute`) and the previous
  one is marked `is_current = false`, preserving history. The claim status and
  total are recomputed. The dispute outcome is `overturned` if the decision or
  payable changed, else `upheld`.

This is why adjudication is versioned rather than overwritten.

---

## Sensitive data (PHI)

PHI is isolated to specific columns: `member.full_name`, `member.date_of_birth`,
`claim.provider_name`, `claim.provider_identifier`, `claim_line_item.diagnosis_code`,
and `dispute.reason`. RLS is enabled (default-deny) on every table; only the
server-side service role accesses data. API responses do not echo PHI, and logs
record only identifiers/status/counts.

## Conventions

- UUID primary keys (`gen_random_uuid()`); human-readable `claim_number` /
  `policy_number` for display.
- Money is `NUMERIC(12,2)`; coinsurance `NUMERIC(5,4)` constrained to 0..1.
- Status columns are `text` + `CHECK` (easy to evolve in migrations); lookups
  (`service_type`, `reason_code`) are tables for referential integrity.
- Timestamps are `timestamptz`; `updated_at` maintained by a trigger.

## Out of scope

Authentication, policy purchase / enrollment, member or provider management,
notifications, dashboards, and multi-role access control. Provider details are
stored on a claim but providers are not managed as records.
