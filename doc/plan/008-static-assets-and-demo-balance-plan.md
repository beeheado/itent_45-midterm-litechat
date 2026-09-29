# HeavyChat Static Assets and Demo Balance Plan

- **Created:** 2026-09-29T09:06:11+00:00
- **Study:** [`doc/study/008-static-assets-and-demo-balance-study.md`](../study/008-static-assets-and-demo-balance-study.md)
- **Status:** Execution authorized by the user's fix request.
- **Scope:** Static asset URLs, CDN verification, demo accounts, tests, documentation, and the requested single commit.

## Checklist

- [x] Set `STATIC_URL` to an absolute `/static/` path and add a test for local assets and all required head CDN references.
- [x] Move/implement the `setup_demo` command at `chat/management/commands/setup_demo.py`, provisioning `luis` and `beeheado`, each with a default profile, personal account, and one ledger-backed 1,000-credit deposit.
- [x] Preserve password behavior and verify repeat invocation does not duplicate deposits or reset balances.
- [x] Update handoff/operations docs to describe both demo users and correct static URL behavior.
- [x] Run `python manage.py setup_demo`, `.venv/bin/python manage.py check`, and `.venv/bin/python -m pytest`.
- [x] Review the scoped diff, preserve pre-existing staged work, and create exactly `fix: load tailwind and cdn dependencies in base template and seed credits for active user` on `main`.

## Dependencies and Verification

- The seeder depends on the migrated SQLite schema and `deposit_credits()` transaction/idempotency behavior.
- The template test verifies root-absolute app static links and the Tailwind, HTMX, marked.js, DOMPurify, highlight.js, and dark theme references.
- All requested commands must complete successfully before committing. Do not include pre-existing staged changes in the requested fix commit.
