# AI Collaboration Artifacts

Raw [Claude Code](https://claude.com/claude-code) session logs (`.jsonl`) for this
project. **This is the complete set — every project session is included, nothing
was removed or curated out**, including short interrupted sessions, so the trail
is honest end-to-end. The logs are committed verbatim (raw `.jsonl`, not summaries
or exports). They contain no secrets (the Supabase service-role key never appears;
only the `YOUR_SERVICE_ROLE_KEY` placeholder from `.env.example`).

Each filename follows `YYYY-MM-DD_claude-code_<phase>_<session-id>.jsonl`. The date
prefix is approximate; the "active window" column below comes from the actual
message timestamps inside each log.

## Sessions

| Log | ~Lines | Active window (UTC) | What it covers |
|---|---|---|---|
| `..._assignment-analysis_3e2235fa.jsonl` | 15 | Jun 3 | Reading the brief — problem framing |
| `..._build-engine-tests-api_1549d6e8.jsonl` | 1284 | Jun 3 13:56–17:02 | Test-first adjudication engine, validation, FastAPI endpoints, API docs, gap analysis |
| `..._api-docs_f8c046b0.jsonl` | 94 | Jun 3 | Backend correctness + documenting the endpoints |
| `..._interrupted-stub_cc1f7c2b.jsonl` | 9 | Jun 3 | Interrupted session (no assistant turns) |
| `..._framing-domain-schema_d8b81f67.jsonl` | 1161 | Jun 4 03:51–08:09 | Supabase setup, schema + migrations, domain modeling, persistence, human steering (AskUserQuestion) |
| `..._review-fixes_4b5d4ed4.jsonl` | 786 | Jun 4 | Reviewer report + lifecycle/dispute fixes (forked/resumed twin of the session below) |
| `..._review-qa-atomicrpc-docs_48cc9682.jsonl` | 950 | Jun 4 15:21–onward | Strict review → corrections (manual review, line-level disputes, 2-dp money) → QA regression → atomic-submission RPC → recreated docs → repo flatten → README. The most recent / live session. |
| `..._reviewer-pass_2df7ba2c.jsonl` | 143 | Jun 4 | Read-only assignment-reviewer evaluation |
| `..._reviewer-pass_dea90f33.jsonl` | 169 | Jun 4 | Read-only assignment-reviewer evaluation |
| `..._interrupted-stub_68b69334.jsonl` | 15 | Jun 4 | Interrupted session (no assistant turns) |
| `..._interrupted-stub_e752b515.jsonl` | 9 | Jun 4 | Interrupted session (no assistant turns) |

## Phase coverage (assignment requirement)

- **Problem framing** — `3e2235fa`, opening of `1549d6e8`.
- **Domain modeling & schema** — `d8b81f67`, `1549d6e8`.
- **Planning** — `d8b81f67`, `1549d6e8`.
- **Coding (engine, API, persistence)** — `1549d6e8`, `d8b81f67`, `f8c046b0`, `48cc9682`/`4b5d4ed4`.
- **Testing** — `1549d6e8` (test-first), `48cc9682` (integration tests).
- **Documentation** — `f8c046b0`, `48cc9682`, `1549d6e8`.
- **QA / review** — `2df7ba2c`, `dea90f33`, `4b5d4ed4`, `48cc9682`.

## Honest notes

- The three `interrupted-stub` logs have 3 user messages and **0 assistant turns** — they are abandoned/restarted sessions, included only for completeness.
- `4b5d4ed4` and `48cc9682` overlap (the session was forked/resumed); both are kept rather than dropping one.
- **Domain *research* is the thinnest-evidenced phase** — the domain was reasoned about heavily inside the modeling sessions, but there is little external-source research captured in the logs.
- `48cc9682` is the live session at submission time, so the final commit/push moments may post-date the captured copy.
