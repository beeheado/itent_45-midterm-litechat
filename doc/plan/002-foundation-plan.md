# HeavyChat Foundation Plan

- **Created:** 2026-09-29T05:38:23+00:00
- **Updated:** 2026-09-29T05:44:21+00:00
- **Study:** [`doc/study/002-foundation-study.md`](../study/002-foundation-study.md)
- **Status:** Phase 2 complete and merged to `main`; awaiting Phase 3 approval.
- **Scope:** Bootstrap the Django/ASGI foundation, dotenv settings, exact direct-dependency pins, pytest smoke test, and living architecture documentation. Do not implement chat/domain application behavior in this phase.

## Execution Checklist

### 1. Dependencies and Project Scaffold

- [x] Add `requirements.txt` with exact direct pins: Django 5.1.15, openai 3.20.0, pytest 9.1.1, pytest-django 4.14.0, python-dotenv 1.2.3, tiktoken 0.14.0, and uvicorn 0.54.0. Django 5.1.15 satisfies the requested `>=5.0,<5.2` bound; retain the unsupported-series deployment warning in documentation.
- [x] Create an ignored `.venv` and install the pinned requirements without reading or altering the existing `.env` values.
- [x] Generate the Django project named `heavychat` at the repository root, with root `manage.py` and `heavychat/asgi.py` as the ASGI entry point. Keep the generated WSGI module only as Django's default scaffold; configure and document Uvicorn as the server.
- [x] Extend `.gitignore` for the SQLite development database and add a placeholder-only `.env.example` for `SECRET_KEY`, `DEBUG`, `OPENAI_PROXY_KEY`, and `LITECHAT_PROXY_BASE_URL`.

### 2. Settings and Test Harness

- [x] Load the repository `.env` with `python-dotenv` without overriding process environment values. Configure typed `DEBUG`, `SECRET_KEY`, `OPENAI_PROXY_KEY`, and normalized `LITECHAT_PROXY_BASE_URL` settings. Use an ephemeral key only for local debug when `SECRET_KEY` is absent; fail configuration when debug is disabled without an explicit key.
- [x] Configure SQLite at `BASE_DIR / "db.sqlite3"` and set `ASGI_APPLICATION = "heavychat.asgi.application"`.
- [x] Add `pytest.ini` with `DJANGO_SETTINGS_MODULE = heavychat.settings` and pytest-django-compatible test discovery.
- [x] Add `tests/test_foundation.py` asserting Django app setup, allowed Django 5 version, ASGI setting, SQLite engine, and resolved setting types without printing or comparing secret values.

### 3. Rendezvous and Documentation

- [x] Install dependencies into the virtual environment and run `pytest` from the repository root.
- [x] Run `python manage.py check` and confirm the ASGI application imports. Record that the check does not validate an external LiteChat request or production SSE deployment.
- [x] Update `doc/wiki/architecture.md` with project layout, pinned versions, environment settings, local ASGI command, SQLite scope, and the unsupported Django 5.1 production risk.
- [x] Review the staged diff and verify `.env`, SQLite data, and generated caches are not committed.
- [x] Commit with `feat: initialize django 5 asgi project and test harness` and merge into `main` only after tests and system checks pass.

## Verification Record

- `pytest`: 1 passed.
- `python manage.py check`: no issues.
- `pip check`: no broken requirements.
- ASGI application import and production-mode missing-`SECRET_KEY` guard: passed.
- `.env`, `.venv/`, `db.sqlite3`, and generated Python caches are excluded from the commit.
- Feature commit `2ae5445` was fast-forward merged into `main`.

## Stop Condition

Complete Phase 2 only. Do not create chat apps, domain models, routes, templates, or streaming behavior from Phase 3. After verification, documentation sync, commit, and merge, halt for the user's next instruction.
