# HeavyChat Final Verification and Packaging Study

- **Created:** 2026-09-29T08:13:58+00:00
- **Status:** Study complete; Phase 6 execution is authorized by the user's request.
- **Scope:** Final docs/wiki consolidation, reproducible demo data, SimGen removal, security/worktree review, test/system checks, and midterm packaging.

## Verified Baseline

- `main` contains the Phase 1 through Phase 5 commits, including the Phase 5 UI and fetch-based SSE client. Local feature branch pointers are ancestors of `main`.
- The current UI still contains a SimGen placeholder route and navigation link. The final instruction excludes SimGen completely, so remove that placeholder from the deliverable.
- There is no root README or operations wiki. `AGENTS.md` and `doc/study/001-architecture-study.md` exist but are untracked; `sweep_routes.sh` is an untracked scratch script.
- `.env`, `.venv/`, and `db.sqlite3` are ignored. `.env` contains credentials and must remain untouched and untracked.
- The current suite has 28 tests across foundation, models/ledger, streaming, and view workflows. Tests replay captured provider fixtures and mocks rather than making live provider calls.
- Django 5.1.15 is officially unsupported, and SQLite cannot validate multi-worker row-lock behavior.

## Readiness Evaluation

### Test Coverage

The test suite covers Decimal ceiling math, ledger constraints/idempotency and reserve/settle/release behavior, captured SSE parsing/termination and failure recovery, model/session/profile/memory/top-up views, and the foundation settings. A Node syntax check covers the fetch client, but there is no full browser automation, screenshot comparison, accessibility audit, or CDN outage test. The deliverable is ready for a local midterm demonstration after final verbose tests and Django checks; this is not production acceptance testing.

### Ledger Auditability

Credit mutations use atomic services and append-only `CreditLedger` entries with unique idempotency keys. Completed usage is recorded once per assistant message and linked to its reserve with request-time rate snapshots. The demo seed must use `deposit_credits()` for its initial credits and a stable idempotency key so repeat setup runs do not reset balances or add credits twice. It must not edit balances directly.

The ORM guards are not tamper-proof against privileged raw SQL or bulk updates. SQLite does not provide effective row-level `select_for_update()` serialization. Keep these limitations in final documentation.

### Deliverable Readiness

- Provide one idempotent `setup_demo` management command that creates `luis`, `[Personal] LUIS CLARENCE MARIANO`, a sample profile, and one sample memory item, with 1,000 initial credits posted to the ledger.
- Generate a random demo password on first creation unless `HEAVYCHAT_DEMO_PASSWORD` is supplied. Display a generated password only once in the invoking terminal; never store it in source or logs. Re-running the command must leave user credentials and balance unchanged.
- Track `AGENTS.md` and the original Phase 1 study as requested. Ignore `sweep_routes.sh` instead of deleting or otherwise altering the user's scratch file.
- Consolidate the architecture, domain, provider, streaming, UI, and operations wiki. The README must clearly distinguish the captured provider response from user-supplied baseline model rates.
- Remove the SimGen placeholder route, page, and navigation because the final scope is strictly HeavyChat.
- Django 5.1.15 remains unsupported. Phase 6 documents this; it does not override the explicit stack constraint.

## Implementation Decision

Proceed with final packaging, a deterministic and auditable demo seed, SimGen removal, tracked workflow history, README and wiki sync, and the requested verbose test/check runs. Add `.env`-based setup guidance without reading or committing secrets. Report remaining production risks and halt after the final commit/merge.
