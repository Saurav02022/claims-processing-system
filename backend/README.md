# Backend — Claims Processing System

This is the backend service (Python + FastAPI over Supabase/Postgres).

**Full setup, run, test, and API documentation is in the root
[`../README.md`](../README.md).** Read that first.

## Quick start

```bash
# from this backend/ directory
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                # fill in SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

uvicorn app.main:app --reload                       # http://127.0.0.1:8000/docs
pytest -q                                           # run the test suite
```

Before submitting claims, apply the SQL migrations in `supabase/migrations/`
to your Supabase project and seed demo data with `python -m scripts.seed_demo`
(details in the root README).

## Layout

- `app/` — FastAPI app, services, repository, and the pure `domain/` engine
- `supabase/migrations/` — database schema (source of truth)
- `scripts/seed_demo.py` — demo plan/policy/coverage rules
- `tests/` — engine, API, and DB-constraint tests
- `docs/` — domain model, decisions, self-review, and the assignment brief
