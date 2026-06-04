# Claims Processing System

A claims processing service for a health insurer. Members submit claims made of
line items; the system adjudicates each line item against the policy's coverage
rules — deciding whether it is covered, how much is payable, and **why** — tracks
the claim and its line items through their lifecycle, and lets members dispute a
decision (which triggers re-adjudication).

Built with **Python + FastAPI** over **Supabase (Postgres)**. The adjudication
logic is a pure, dependency-free domain layer; persistence and the HTTP interface
sit around it.

> Forward Deployed Engineer take-home. The full assignment brief lives in
> [`docs/problem_statement.md`](docs/problem_statement.md) and
> [`docs/candidate_assignment_instructions.md`](docs/candidate_assignment_instructions.md).

---

## What it does

- **Submit a claim** with one or more line items (service type, date, billed amount).
- **Adjudicate each line** against the plan's coverage rules: coverage check,
  plan deductible, copay, coinsurance, annual money limit, annual visit limit,
  and a manual-review threshold — in that order.
- **Calculate the payable amount** per line and roll the line decisions up into a
  claim status (`approved` / `partially_approved` / `denied` / `under_review`).
- **Explain every decision** with reason codes (e.g. `NOT_COVERED`,
  `ANNUAL_LIMIT_EXCEEDED`, `DEDUCTIBLE_APPLIED`).
- **Track usage across claims** (deductible / limit / visits) via accumulators.
- **Dispute a line decision** and resolve it through versioned re-adjudication,
  with an append-only status-history audit trail.

---

## Tech stack

| Layer | Choice |
|---|---|
| Language / framework | Python 3.11+, FastAPI |
| Database | Supabase (PostgreSQL) via `supabase-py` (PostgREST) |
| Config | `pydantic-settings` (env vars) |
| Tests | `pytest` |

---

## Project structure

```
app/
  main.py              FastAPI app + routes
  schemas.py           API request/response models
  claims_service.py    orchestration (submit, get, dispute, resolve, review)
  claims_repository.py  Supabase persistence + repository abstraction
  config.py / db.py    settings + Supabase client
  domain/              pure adjudication engine (no DB/framework deps)
    adjudication.py, models.py, enums.py
supabase/migrations/   SQL schema (source of truth)
scripts/seed_demo.py   demo plan/policy/coverage rules for a live demo
tests/                 engine, API, and DB tests
docs/                  domain model, decisions, self-review, assignment brief
ai-artifacts/          raw Claude Code session logs
```

---

## Prerequisites

- **Python 3.11+**
- **A Supabase project** (free tier is fine). The app talks to Supabase over its
  REST API, so you need the project URL and a service-role key. There is no
  offline/in-memory database mode — the API needs a real Supabase project.

---

## Setup

```bash
git clone <your-repo-url> claims-processing-system
cd claims-processing-system

python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

pip install -r requirements-dev.txt # runtime deps + pytest

cp .env.example .env                # then edit .env (see below)
```

Fill in `.env`:

```
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY
```

Both values are in the Supabase dashboard under **Project Settings → API**.
`.env` is git-ignored — never commit it.

---

## Database setup

The schema is defined by the SQL migrations in
[`supabase/migrations/`](supabase/migrations) and is the single
source of truth. Apply them to your Supabase project **in filename order** using
the Supabase dashboard **SQL Editor** (paste and run each file):

1. `20260604044439_baseline_schema.sql` — tables, constraints, RLS, triggers
2. `20260604044452_seed_reference_data.sql` — service-type catalog + reason codes
3. `20260604044802_schema_hardening.sql` — advisor fixes (indexes, search_path)
4. `20260604120000_review_completion.sql` — manual-review trigger + reason codes
5. `20260604130000_atomic_claim_submission.sql` — `submit_claim_atomic()` RPC

Then load a demo plan, coverage rules, member, and policy to submit claims against:

```bash
# from the project root, with the venv active and .env filled in
python -m scripts.seed_demo
```

It prints a `policy_id` to use in requests. The demo plan has a $200 annual
deductible and these rules: PHYSIO (copay $20, visit limit 10), DENTAL (annual
limit $1000, 20% coinsurance), OPTICAL (manual-review threshold $500),
MENTAL_HEALTH (not covered).

---

## Run

```bash
# from the project root, venv active
uvicorn app.main:app --reload
```

- API base: `http://127.0.0.1:8000`
- Interactive docs (Swagger UI): `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/health`

---

## API

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/health` | Liveness check |
| `POST` | `/claims` | Submit a claim with line items; returns the adjudicated result |
| `GET`  | `/claims/{claim_id}` | Fetch a persisted, adjudicated claim |
| `POST` | `/claims/{claim_id}/disputes` | Open a dispute on a line of a claim |
| `POST` | `/disputes/{dispute_id}/resolve` | Resolve a dispute (re-adjudicates the line) |
| `POST` | `/claims/{claim_id}/lines/{line_id}/review` | Complete manual review of a `needs_review` line (`approved`/`denied`) |

### Example: submit a claim

Use the `policy_id` printed by `seed_demo`:

```bash
curl -X POST http://127.0.0.1:8000/claims \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "<POLICY_ID>",
    "line_items": [
      {"service_type_code": "PHYSIO",        "service_date": "2026-03-01", "billed_amount": 250},
      {"service_type_code": "DENTAL",        "service_date": "2026-03-02", "billed_amount": 500},
      {"service_type_code": "MENTAL_HEALTH", "service_date": "2026-03-03", "billed_amount": 80},
      {"service_type_code": "OPTICAL",       "service_date": "2026-03-04", "billed_amount": 600}
    ]
  }'
```

This returns one approved line (deductible + copay), one approved line
(coinsurance), one denied line (`NOT_COVERED`), and one `needs_review` line
(over the review threshold) — so the claim rolls up to `under_review`. Each line
carries its money breakdown and reason codes. Copy the returned `claim_id` and
`GET /claims/{claim_id}` to read it back, or a line's `id` to open a dispute.

### Example: complete a manual review

The `OPTICAL` line above is `needs_review`. A reviewer resolves it (taking the
claim out of `under_review`):

```bash
curl -X POST http://127.0.0.1:8000/claims/<CLAIM_ID>/lines/<LINE_ID>/review \
  -H "Content-Type: application/json" \
  -d '{"decision": "approved"}'
```

`approved` keeps the line's computed payable and re-rolls the claim up;
`denied` zeroes the line's payable. Either way a new adjudication version is
recorded (`triggered_by = review`) with a status-history entry.

---

## Tests

```bash
# from the project root, venv active
pytest -q
```

What runs:
- **Adjudication engine** — coverage, deductible/copay/coinsurance and ordering,
  annual/visit limits, review threshold, claim roll-up, rounding, invariants,
  rule precedence, dispute determinism (pure unit tests, no DB).
- **API + service layer** — `tests/test_api.py` drives the FastAPI app with a
  fake repository (offline), covering submit/get/dispute flows, validation and
  error mapping, partial approvals, and PHI non-leakage in responses.
- **DB constraints** — `tests/test_schema_constraints.py` runs only when Supabase
  env vars are set; otherwise it is skipped. It verifies CHECK constraints, the
  one-current-adjudication index, accumulator uniqueness, and FK cascade against
  the live database (each test rolls back / cleans up after itself).
- **Repository integration** — `tests/test_repository_integration.py` (also gated
  on Supabase env vars) drives the real `SupabaseClaimRepository` end-to-end:
  submit → read-back, accumulator persistence across claims, dispute open/resolve
  (overturn + versioning), and manual-review approve/deny. Each test seeds and
  deletes its own isolated policy graph.

The engine and API tests need no database or running server.

---

## Design & documentation

- [`docs/domain-model.md`](docs/domain-model.md) — entities,
  relationships, ERD, coverage-rule modeling, and the claim / line-item state
  machines.
- [`docs/decisions.md`](docs/decisions.md) — key decisions,
  trade-offs, and assumptions.
- [`docs/self-review.md`](docs/self-review.md) — honest
  assessment of what is solid and what is rough.

---

## Known limitations (by design / scope)

These are deliberate and documented in `decisions.md` / `self-review.md`:

- **Claim submission is atomic.** The full submission write runs in one
  transaction via the `submit_claim_atomic` Postgres function (`client.rpc(...)`),
  so a mid-write failure rolls back cleanly. The smaller dispute-resolution and
  manual-review write paths are still sequential over PostgREST.
- **Dispute resolution is line-level.** You dispute a specific line
  (`line_item_id` is required); a single claim-wide dispute action is not offered.
- **Aggregate overflow.** Per-line `billed_amount` is bounded to the
  `NUMERIC(12,2)` range; a claim whose *total* exceeds it is an untested edge.
- **No authentication / authorization.** The service uses the Supabase
  service-role key server-side; there is no end-user auth (out of scope).

### Out of scope

User registration/login, policy purchase or enrollment, member/provider
management, notifications, dashboards, and multi-role access control — per the
assignment brief.
