# Forward Deployed Engineer - Take-Home Assignment (Level 1)

## The Problem

Build a **Claims Processing System** for an insurance company.

Members submit claims for reimbursement. The system must determine what's covered, how much to pay, and track the claim through its lifecycle.

---

## Context

An insurance company processes claims like this:

- A **member** has a **policy** with coverage rules (what's covered, limits, deductibles)
- The member incurs an expense and submits a **claim** with line items
- Claims contain member names, diagnosis codes, and provider details. This is sensitive health data — your design decisions should reflect that.
- The system must **adjudicate** each line item: Is it covered? How much do we pay?
- Claims move through states: submitted → under review → approved/denied → paid
- Members can dispute decisions

The interesting problems:

- How do you model coverage rules? (service type X is covered up to $Y per year)
- How do you track what's already been used against limits?
- What happens when a claim has 5 line items and 3 are covered, 1 is denied, 1 needs review?
- How do you explain to a member why something was denied?
- What's the state machine of a claim vs. a line item?

---

## Your Assignment

Build a working system that processes insurance claims.

A working system:

- Accepts claim submissions with line items
- Applies coverage rules to determine payable amounts
- Moves claims through lifecycle states
- Produces explanations for every decision
- Has an interface through which you can demonstrate it — a REST API, a web UI, or a CLI. Pick one. The interface exists so you can walk us through your solution.

You decide:

- The domain model
- How coverage rules are represented and applied
- What states exist and how transitions work
- How to handle partial approvals
- How deep to go

---

## Scope of the Application

The system covers only the flows described in the Context section above.

**In scope:**

- Submitting a claim with line items
- Adjudicating each line item against coverage rules
- Tracking claim and line-item states through their lifecycle
- Producing explanations for coverage decisions
- Members disputing decisions

**Out of scope:**

- User registration, login, or authentication
- Policy purchase or enrollment flows
- Member or provider account management
- Email notifications or alerts
- Reporting dashboards or analytics
- Admin panels for managing policies, members, or providers
- Multi-tenant or multi-role access control

These are adjacent real-world concerns but they are not what we are evaluating. Building them will not improve your score.

---

## Deliverables

### 1. Working System

Runs locally. Processes claims against coverage rules.

### 2. Domain Model Documentation

Your entities, relationships, state machines. How did you model coverage rules?

### 3. Decisions & Trade-offs

What you built, what you didn't, what assumptions you made about the domain.

### 4. AI Collaboration Artifacts

Chat exports, prompts, what AI got wrong. Include the raw JSONL session logs from your coding agent (Claude Code, Codex CLI, Cursor, etc.).

### 5. Self-Review

What's good, what's rough, what you'd flag.

---

## Time

24-48 hours max.

---

## What We're Looking For

| Signal | What It Tells Us |
|---|---|
| **Domain decomposition** | Can you model policies, claims, coverage rules cleanly? |
| **Rule representation** | How do you structure coverage logic? |
| **State management** | Claims and line items have lifecycles — did you model them? |
| **Edge case thinking** | Partial approvals, limit exhaustion, retroactive changes? |
| **Explanation capability** | Can the system say WHY something was denied? |

---

## What We're NOT Specifying

- How to represent coverage rules (code, config, DSL?)
- Which specific rules to implement
- Database schema
- API design
- UI requirements

That's on you.

---

## Submission

Make sure your submission contains the following:

| Required | Description |
|---|---|
| `app/` | Your application code |
| `docs/domain-model.md` | Entities, relationships, state machines |
| `docs/decisions.md` | What you built, what you didn't, assumptions |
| `docs/self-review.md` | Honest assessment of your own code |
| `ai-artifacts/` | **Raw JSONL session logs are mandatory** — plus chat exports, prompts, AI corrections. Submissions without JSONL logs will not be reviewed. |
| `README.md` | Setup and run instructions |
| `.git/` | Your commit history (zip must include this folder) |

Submit as a zip/tarball. We review your commit history to understand how you approached the problem.

---

## Note

If you proceed to the next round, we'll extend this system together.

---

**Show us how you model a domain.**

