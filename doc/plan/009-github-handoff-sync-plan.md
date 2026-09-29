# HeavyChat Handoff and GitHub Sync Plan

- **Created:** 2026-09-29T09:11:29+00:00
- **Study:** [`doc/study/009-github-handoff-sync-study.md`](../study/009-github-handoff-sync-study.md)
- **Status:** Execution authorized by the user's request.
- **Scope:** Complete `HANDOFF.md`, stage all current project work excluding ignored local-only files, verify, commit, and push `main`.

## Checklist

- [x] Update `HANDOFF.md` with phases 1-6, full stack, provider contract/key, active model IDs/rates, ledger/reservation/settlement rules, frontend features, and current demo accounts.
- [x] Include the exact migration, catalog, demo setup, test, and Uvicorn commands; use the actual current test count.
- [x] Stage all modified and untracked project files; confirm `.env`, `.venv/`, and `db.sqlite3` are excluded.
- [x] Run `.venv/bin/python -m pytest` and confirm the suite result: 31 passed.
- [ ] Commit all staged/current project progress on `main` as `chore: update handoff documentation and sync release progress`.
- [ ] Push with `git push origin main`, then confirm remote tracking, latest commit, and a clean worktree.

## Verification and Dependencies

- The remote URL is already configured correctly; push depends on GitHub network access and credentials.
- Test count must come from the verification run, not the historical parenthetical in the request.
- Commit review must confirm ignored secrets, virtualenv, and local SQLite data are absent from the commit.
