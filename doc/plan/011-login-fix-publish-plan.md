# HeavyChat Login Fix Publish Plan

- **Created:** 2026-09-29T12:53:23+00:00
- **Study:** [`doc/study/011-login-fix-publish-study.md`](../study/011-login-fix-publish-study.md)
- **Status:** Execution authorized by the user's request.
- **Scope:** Stage clone-required login fix and project progress, run checks, commit, and push `main`.

## Checklist

- [x] Add an ignore rule for the local session export; preserve the file but exclude it from Git.
- [x] Stage all project changes, including auth routes, login template, tests, and documentation; confirm `.env`, `.venv/`, and `db.sqlite3` are excluded.
- [x] Run `.venv/bin/python manage.py check` and `.venv/bin/python -m pytest`; confirm 34 tests pass.
- [x] Commit on `main` as `fix: add styled accounts login route and finalize demo setup`.
- [x] Push with `git push origin main` and verify local `main` equals `origin/main` with a clean worktree.

## Verification

- `origin` already points to the requested GitHub repository.
- Review the staged filenames and diff before commit; do not stage local credentials, database, virtualenv, or session transcript.
