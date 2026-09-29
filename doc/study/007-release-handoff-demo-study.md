# HeavyChat Release Handoff and Demo Setup Study

- **Created:** 2026-09-29T08:46:18+00:00
- **Status:** Study complete; execution is authorized by the user's release request.
- **Scope:** Add `HANDOFF.md`, confirm setup documentation in the README/wiki, expose demo setup at `chat/management/commands/setup_demo.py`, run the full pytest suite, and create the requested single conventional commit on `main`.

## Verified Facts

- The current branch is `main`, based on the Phase 5 commit. The worktree is already dirty with release-oriented edits and untracked documentation/tests; these are pre-existing and must be preserved.
- The repository has a Django 5.1 ASGI app, SQLite database, HTMX UI, vanilla `fetch()` SSE client, and a LiteChat OpenAI-compatible provider adapter.
- The provider route is `https://proxy.litechat.ai/openai/v1/chat/completions`; configuration reads `OPENAI_PROXY_KEY`. The captured stream includes content and reasoning deltas, then usage, then `[DONE]`.
- `ModelCatalog` stores Luna, Terra, and Sol models/rates in `core/fixtures/model_catalog.json`. One credit is $0.01, so 1,000 credits represent $10.00.
- An idempotent demo seeder and a database-backed test already exist under `core/management/commands/` and `tests/`; the requested `chat` command path does not yet exist.
- The README and multiple wiki pages already contain in-progress release information. `doc/wiki/operations.md` includes the requested setup commands, while other pages need consistency checks and a handoff document is absent.

## Tradeoffs and Risks

- Keep the existing seeder's ledger-backed idempotency rather than setting `credit_balance` directly. Expose the requested `chat` command path by delegating to that implementation, avoiding duplicated account/deposit logic while retaining the existing tests.
- The catalog rates are supplied baseline configuration, not verified provider pricing. Handoff material must state this distinction and must not imply live provider availability was tested.
- Local run instructions require Python dependencies, a local `.env`, schema migration, model fixture load, a seeded demo user, and Uvicorn. Live chat additionally requires a valid proxy key.
- Django 5.1.15 is unsupported and SQLite does not establish multi-worker ledger safety. These are release/demo limitations, not blockers for the requested local demonstration.
- Several unrelated or broader in-progress changes are present. Do not revert or silently expand their scope; commit only files necessary for this requested release outcome.

## Assumptions and Open Questions

- User-provided phase completion and the reported prior 28-test result are accepted as context; this work will independently run the current full test command.
- “Default UserProfile” means an idempotently created profile with model defaults; the existing implementation also provisions sample prompt/memory context.
- No unresolved external provider input is needed; the captured stream fixture and its provenance are already recorded in the wiki.

## Decision

Proceed with a focused release handoff, exact setup-command documentation, and the requested app-level command entry point. Preserve existing uncommitted work, verify via `.venv/bin/python -m pytest`, and make the requested commit only if verification succeeds.
