# Candidate Instructions

## What This Assignment Tests

This isn't about whether you can build a CRUD app. It's about:

- **Domain modeling** - Can you research a problem domain and decompose it into the right abstractions?

  Onboarding quickly into complex client domains is part of this job — that's why we chose the insurance domain. Treat domain research as part of the work, not a preliminary step. Research claims processing, coverage rules, denial taxonomies, and adjudication logic before and alongside building.

  You don't need to be an insurance expert, but you should be able to speak in the language you've modeled in your code and explain *why* you modeled a business rule a certain way. This is what lets you think through business rule changes without depending entirely on AI — otherwise you can't provide meaningful feedback or take ownership of the final code.
- **Engineering judgment** - Can you make good decisions about what to build and what to skip?
- **Test-driven thinking** - Do you write tests that encode your understanding of the domain, not just verify UI behavior?
- **AI collaboration** - Can you work effectively with AI tools while staying in control?
- **Self-awareness** - Do you know what's good and what's rough in your own work?

---

## Ground Rules

- **Ship a working application, not just a passing test suite.** We will clone your submission, set it up from your README, and run the flows you built. If it doesn't run, the tests don't count.
- **Self-review the work.** Name what's broken, thin, or skipped — and the trade-off that put it there. A calibrated gap-list with reasoning earns more credit with us than polished completeness.
- **The chat is read alongside the code.** Submit your raw AI conversations with the work — the code tells us what shipped; the chat tells us how it got there, and who was steering. Your trail of commits, conversations, and revisions tells us more about your approach than a single tidy drop.
- **You are the designer of this system.** You should be able to walk through any part of it — what it does, why it's there, where it could break.
- **The code matters as much as what it produces.** Good code is its own bar.

---

## Time

24 to 48 hours. How you allocate it is up to you.

---

## AI Tools

Use them. We want to see how you work with AI, not without it.

**Non-Negotiable Requirement:** Submit raw `.jsonl` session logs covering every phase of your work — problem framing, domain research, planning, coding, documentation, testing, and QA. Use whichever coding agents you like (Claude Code, Codex CLI, Cursor, etc.), and feel free to switch or combine them — but every phase must be done inside a coding agent that produces `.jsonl`, and the logs for all of them must be in the submission. We need the complete trail, not just the coding portion.

Curated Markdown summaries, `.json` array dumps, or screenshots DO NOT substitute — only raw `.jsonl` lets us separate your contribution from the agent's. DO NOT use a tool that doesn't give you `.jsonl` files for any phase.

> **Mandatory — do not skip.** Not sure where your logs are? Just ask your agent — "where are my session logs / JSONL files?" is a valid prompt and it should be able to locate them for you. Submissions without complete session logs (covering all phases) will BE REJECTED by default.

We'll look at:
- How you prompt
- Whether you iterate or just accept
- What you caught that AI got wrong
- Whether you understand the code you submitted

---

## What to Submit

| Deliverable | What We Want to See |
|-------------|---------------------|
| **`.git` folder** | Your commit history — we review how you approached the problem. |
| **JSONL session logs** | Raw session logs covering every phase (framing, research, coding, documentation, testing, QA). One or many agents — but the logs must cover all phases. Shows how you think, prompt, and iterate. |
| **README** | Setup instructions. We will clone your submission and run it — if it doesn't run, the review stops. |
| **Domain model doc** | Your entities, relationships, state machines. Why this decomposition? |
| **Decisions doc** | What you built, what you didn't, what assumptions you made. |
| **Self-review** | Honest assessment. What's good? What's rough? What would you change with more time? |
| **Working system + tests** | Does what it claims. Tests encode domain rules, not just assert HTTP status codes. |

> **Submissions missing any required deliverable will be rejected.** Don't let a missing doc cost you the opportunity.

**Submission format:** Zip/tarball with `.git` folder included. Commit history matters.

---

## What We Don't Prescribe

- Technology stack
- How to structure your code
- Which edge cases to handle
- How sophisticated to make it
- What the interface looks like

**Make decisions. Justify them.**

---

## What Makes a Good Submission

**Coherent scope.** A system that does 3 things well beats one that does 10 things poorly.

**Clear domain model.** We should understand your abstractions and why you chose them.

**Tests written before code.** Your git history should show tests appearing before or alongside implementation — not added at the end. Tests that specify behavior ("when a claim is submitted with a duplicate line item, it should...") are far more valuable than tests that just check return types.

**Honest self-assessment.** "This is rough because..." shows more maturity than "everything is perfect."

**Effective AI use.** Using AI to explore options and iterate is good. Accepting walls of code without review is a red flag.

---

## What Gets Rejected

**Submissions missing any required deliverable will be rejected.** Beyond that, these are the patterns that lead to a rejection:

- No AI session logs, or partial logs covering only some phases (we can't evaluate your process)
- No `.git` folder or a single-commit dump (we can't see how you worked)
- No domain model documentation, or a domain model that doesn't go beyond what AI generated without your input
- Can't explain your own code — if you can't walk through it, it's not yours
- No tests, or tests clearly written after the fact (git history doesn't lie)
- Scattered half-features with no coherence
- Self-review that doesn't match reality

---

## Next Round

If you proceed, we'll extend your system together in a 75-minute pairing session. Write code you can navigate and modify under pressure.

---

## Questions

Logistics → reach out to Sumanth Raj Urs (sumanth@realfast.ai).

Requirements → part of the assignment. Make assumptions, document them.
