# HeavyChat Foundation Study

- **Created:** 2026-09-29T05:37:52+00:00
- **Status:** Study complete; Phase 2 execution is authorized by the user's request.
- **Scope:** Minimal Django project scaffold, ASGI server, pinned foundation dependencies, dotenv settings, SQLite development database, pytest configuration, smoke test, and architecture documentation.

## Verified Workspace Facts

- Python 3.12.3 and pip 24.0 are available; Django is not installed in the current interpreter.
- The project is on `main` at the Phase 1 provider-contract merge. Existing tracked `.gitignore` excludes `.env`, Python caches, and virtual environments.
- The root `.env` contains the names `OPENAI_PROXY_KEY`, `LITECHAT_PROXY_BASE_URL`, and `LITECHAT_API_KEY`; the values were not read. `SECRET_KEY` and `DEBUG` are not currently set there.
- The repository already has provider fixtures and a `tests/` directory. The `heavychat/` Django project package, `manage.py`, dependency manifest, pytest configuration, and foundation test do not yet exist.
- The Python package index reports `Django 5.1.15` as the newest version satisfying `Django>=5.0,<5.2`. It also reports newer Django releases outside that range.
- Django's official download/support page lists Django 5.1 as unsupported, with extended support ending December 3, 2025. Django 5.2 is the supported LTS line, but the requested `<5.2` constraint excludes it.

## Decisions and Tradeoffs

### Django Version Constraint

The requested bound `Django>=5.0,<5.2` admits Django 5.0 and 5.1 only. Pinning the latest compatible release, Django 5.1.15, avoids an earlier patch release while respecting the explicit requirement. However, as of this study date that series receives no security updates or bug fixes. This is an acceptable constraint only for establishing the requested local foundation; it is **not an acceptable production deployment baseline**. Before production, the project should move to a supported Django release (currently the 5.2 LTS line) or obtain a deliberate, time-bounded exception. This risk is recorded rather than silently overriding the user's version requirement.

### ASGI Server

Use Uvicorn rather than Daphne. Uvicorn is an explicit ASGI server and runs Django's generated root application using `uvicorn heavychat.asgi:application`; this makes the actual serving interface unambiguous and avoids changing `INSTALLED_APPS` to replace Django's development `runserver`. `manage.py check` validates Django configuration but does not prove a listening ASGI server works, so the smoke test and import checks should also confirm `ASGI_APPLICATION` points to `heavychat.asgi.application`. A full streaming/deployment test remains outside this foundation phase.

### Dependency Pinning

Pin direct runtime and test dependencies exactly in `requirements.txt` for repeatability. Use the newest versions observed from the configured package index at implementation time, except Django is deliberately constrained as above:

- Django 5.1.15
- openai 3.20.0
- pytest 9.1.1
- pytest-django 4.14.0
- python-dotenv 1.2.3
- tiktoken 0.14.0
- uvicorn 0.54.0

Direct pins stabilize the declared stack, though transitive dependencies remain subject to their upstream constraints; a complete lockfile and hashes are not required for this initial foundation.

### Project Layout and Settings

Keep the generated project small: root `manage.py`, `heavychat/` settings/ASGI/URL modules, `tests/` with the existing fixture subdirectory, and root dependency/pytest configuration. Do not add a chat application or domain models in this phase; those belong to later approved phases.

Use `python-dotenv` to load the ignored root `.env` without overriding variables already supplied by the process environment. Read `SECRET_KEY`, `DEBUG`, `OPENAI_PROXY_KEY`, and `LITECHAT_PROXY_BASE_URL`; never commit `.env` or print secret values. Since the current `.env` lacks `SECRET_KEY` and `DEBUG`, local defaults must allow `manage.py check` and pytest to run without modifying that secret-bearing file. Prefer an ephemeral development-only key and `DEBUG=True` only when local configuration omits them; when `DEBUG=False`, require an explicit `SECRET_KEY`. Keep the proxy key optional for the foundation smoke test, and default the base URL to the verified `https://proxy.litechat.ai/openai/v1` route.

Use SQLite at `BASE_DIR / "db.sqlite3"` for local development and ignore the generated database. A smoke test should check Django app initialization, the ASGI application setting, SQLite selection, and the resolved typed settings without asserting or displaying secret contents.

## Risks and External Dependencies

- The framework constraint selects an unsupported Django series. This is the primary strategic risk and must remain visible in living documentation.
- Package installation depends on the configured Python package index and transitive wheel availability for Python 3.12.
- The real `.env` is user-owned and contains credentials. Do not edit it, stage it, log it, or include its values in tests/docs. Use a placeholder-only `.env.example` if providing onboarding guidance.
- Uvicorn and `manage.py check` establish the ASGI setup but do not verify LiteChat requests, SSE response delivery, or production proxy buffering.

## Implementation Decision

Proceed with the requested minimal foundation using exact dependency pins, Uvicorn, SQLite, dotenv-backed configuration, and a baseline pytest smoke test. Keep application models and views out of scope. Do not deploy this pinned Django 5.1 foundation to production until the support-version decision is revisited. The user's current request authorizes Phase 2 execution after this study and its corresponding plan are written.
