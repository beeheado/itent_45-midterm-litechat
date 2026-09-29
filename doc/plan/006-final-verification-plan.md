# HeavyChat Final Verification Plan

- **Created:** 2026-09-29T08:14:31+00:00
- **Study:** [`doc/study/006-final-verification-study.md`](../study/006-final-verification-study.md)
- **Status:** Execution authorized by the user's request; final-release scope only.
- **Scope:** Final documentation and demo setup, remove SimGen placeholder code, run verification, track required workflow docs, and produce a clean deliverable commit on `main`.

## Execution Checklist

### 1. Demo Setup and Scope Cleanup

- [ ] Add idempotent `setup_demo` management command creating user `luis`, display name `LUIS CLARENCE MARIANO`, `[Personal] LUIS CLARENCE MARIANO`, sample `UserProfile`, and sample `MemoryItem`.
- [ ] Post exactly 1,000 initial credits ($10.00) with `deposit_credits()` and a stable idempotency key; never write `credit_balance` directly or add credits again on repeated runs.
- [ ] Create a one-time random local demo password (or use `HEAVYCHAT_DEMO_PASSWORD`) without storing plaintext or printing an existing password.
- [ ] Remove the SimGen placeholder route, view, page, sidebar item, and tests/docs references from the deliverable.

### 2. Documentation and Repository Hygiene

- [ ] Add an executive root `README.md` with architecture, exact setup/run instructions, autonomous workflow, provider route/fixture findings, reasoning delta behavior, configuration needs, and known production risks.
- [ ] Finalize `doc/wiki/architecture.md`, `domain-models.md`, `streaming-architecture.md`, `provider-contract.md`, and `frontend-ui.md`; add `doc/wiki/operations.md` for setup, demo user, testing, and deployment caveats.
- [ ] Add `HEAVYCHAT_DEMO_PASSWORD` as an optional blank `.env.example` setting and keep real `.env` unchanged/ignored.
- [ ] Track the existing `AGENTS.md` and `doc/study/001-architecture-study.md` without modifying their historical content.
- [ ] Add `sweep_routes.sh` to `.gitignore` instead of deleting or modifying the user-owned scratch file.

### 3. Final Verification and Rendezvous

- [ ] Add tests for `setup_demo` idempotency, ledger-backed initial credit, sample profile/memory creation, and password handling.
- [ ] Run `.venv/bin/python -m pytest -v`, `.venv/bin/python manage.py check`, `makemigrations --check --dry-run`, and `pip check`.
- [ ] Verify all local branches are merged into `main`; `.env`, `.venv/`, `db.sqlite3`, and generated caches are ignored; required workflow files are tracked; no unrelated file is staged.
- [ ] Commit with `chore: finalize heavychat release, demo setup, and comprehensive documentation` and merge into `main` only after verification passes.
- [ ] Confirm the tracked working tree is clean after merge and capture `git log --oneline -n 10` for the final report.

## Stop Condition

Phase 6 is the final requested implementation scope. Do not add features beyond final packaging, demo seeding, scope cleanup, verification, and docs. After the final commit and merge, halt.
