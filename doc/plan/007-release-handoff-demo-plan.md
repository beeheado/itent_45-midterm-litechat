# HeavyChat Release Handoff and Demo Setup Plan

- **Created:** 2026-09-29T08:46:18+00:00
- **Study:** [`doc/study/007-release-handoff-demo-study.md`](../study/007-release-handoff-demo-study.md)
- **Status:** Execution authorized by the user's release request.
- **Scope:** Final handoff, setup documentation, app-level demo command, tests, and one requested commit on `main`.

## Checklist

- [x] Add `HANDOFF.md` covering architecture, LiteChat route/key/SSE contract, supplied Luna/Terra/Sol model IDs and baseline rates, local demo account, setup, and limitations.
- [x] Add the `chat/management/commands/setup_demo.py` entry point, delegating to the existing idempotent ledger-backed setup implementation; include package initializer files as needed.
- [x] Ensure README and applicable `doc/wiki/` setup guidance shows the exact migration, fixture-load, and Uvicorn commands; include the demo seed step.
- [x] Review current management command coverage and add only needed tests for command discoverability/delegation.
- [x] Run `.venv/bin/python -m pytest` and inspect the final diff and worktree.
- [x] Stage only the files required for this release request, then create exactly `chore: finalize heavychat release and demo setup` on `main` if tests pass.

## Dependencies and Verification

- Demo setup relies on the installed `chat` and `core` Django apps, migrated schema, and `deposit_credits()` idempotency.
- Model-tier documentation must be checked against `core/fixtures/model_catalog.json`; provider observations must be checked against the captured fixture and existing provenance wiki.
- The required pytest command must pass before committing. Preserve all existing unstaged work not included in this checklist.
