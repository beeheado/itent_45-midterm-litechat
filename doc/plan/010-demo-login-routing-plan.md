# HeavyChat Demo Login Routing Plan

- **Created:** 2026-09-29T12:45:19+00:00
- **Study:** [`doc/study/010-demo-login-routing-study.md`](../study/010-demo-login-routing-study.md)
- **Status:** Execution authorized by the user's bug report.
- **Scope:** Fix `/accounts/login/` 404 for the local demo flow, add regression coverage, and document how to sign in/reset a lost demo password.

## Checklist

- [x] Include Django's built-in authentication URLconf under `/accounts/`.
- [x] Configure login/logout destinations and add a CSRF-protected styled login template that preserves `next`.
- [x] Add tests for unauthenticated redirect, login rendering, successful credentials, and redirected authenticated access.
- [x] Update operations/handoff docs with the login page and local password recovery guidance.
- [x] Run `.venv/bin/python manage.py check` and `.venv/bin/python -m pytest` (34 tests passed).
- [x] Review the diff and ensure `session-ses_f13a.md` remains untouched.

## Dependencies and Verification

- Uses Django's installed auth/session apps; no new package or migration is required.
- Validated `next` redirects remain Django's responsibility; the default direct-login destination is `/`.
- Tests must prove the original protected URL no longer returns a 404 after authentication succeeds.
